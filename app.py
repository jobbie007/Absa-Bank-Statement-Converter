import fitz
import re
import os
import io
import json
from datetime import datetime
import pandas as pd
from flask import Flask, render_template, request, send_file, flash, redirect, url_for, session
from werkzeug.utils import secure_filename
from flask_session import Session

# --- App Initialization ---
app = Flask(__name__)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
app.config['SECRET_KEY'] = 'a-super-secret-key-that-you-should-change'
Session(app)

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
RULES_FILE = 'custom_rules.json'

# --- Helper Functions for Custom Rules ---
def load_custom_rules():
    """Loads categorization rules from a JSON file."""
    if not os.path.exists(RULES_FILE):
        return {}
    with open(RULES_FILE, 'r') as f:
        return json.load(f)

def save_custom_rules(rules):
    """Saves categorization rules to a JSON file."""
    with open(RULES_FILE, 'w') as f:
        json.dump(rules, f, indent=4)

# --- PDF Parsing and Data Extraction Functions ---
def get_all_lines_from_pdf(pdf_path: str) -> list[str] | None:
    if not os.path.exists(pdf_path): return None
    try:
        all_lines = []
        with fitz.open(pdf_path) as doc:
            for page in doc: all_lines.extend(page.get_text("text").split('\n'))
        return all_lines
    except Exception as e:
        print(f"An error occurred while reading the PDF: {e}"); return None

def group_transactions_from_lines(lines: list[str]) -> list[str]:
    date_pattern = re.compile(r'^\s*\d{1,2}/\d{2}/\d{4}')
    end_markers = ["YOUR PRICING PLAN", "MANAGEMENT FEE"]
    grouped_blocks, current_block = [], []
    for line in lines:
        if any(marker in line.upper() for marker in end_markers): break
        line = line.strip()
        if not line: continue
        if date_pattern.match(line):
            if current_block: grouped_blocks.append(" ".join(current_block))
            current_block = [line]
        elif current_block: current_block.append(line)
    if current_block: grouped_blocks.append(" ".join(current_block))
    return grouped_blocks

def parse_and_sort_transactions(blocks: list[str]) -> list[dict] | None:
    parsed_data = []
    money_pattern = re.compile(r'(\d{1,3}(?:[ ,]\d{3})*[\.]\d{2})')
    date_pattern = re.compile(r'^\s*(\d{1,2}/\d{2}/\d{4})')
    for block in blocks:
        clean_block = " ".join(block.split())
        date_match = date_pattern.match(clean_block)
        if not date_match: continue
        date_str = date_match.group(1)
        amounts_str = money_pattern.findall(clean_block)
        if not amounts_str: continue
        amounts_num = [float(a.replace(',', '').replace(' ', '')) for a in amounts_str]
        balance = amounts_num[-1]
        transaction_amount = amounts_num[-2] if len(amounts_num) > 1 else 0.00
        desc = date_pattern.sub('', clean_block, 1)
        for amount_str in amounts_str: desc = desc.replace(amount_str, '')
        desc = " ".join(desc.split()).strip()
        parsed_data.append({"date_obj": datetime.strptime(date_str, '%d/%m/%Y'), "date": date_str, "description": desc, "amount": transaction_amount, "balance": balance})
    if not parsed_data: return []
    parsed_data.sort(key=lambda x: x['date_obj'])
    try:
        bbf_item = next(item for item in parsed_data if "Bal Brought Forward" in item['description'])
        previous_balance = bbf_item['balance']
    except StopIteration:
        flash("Warning: 'Bal Brought Forward' not found. Debit/Credit columns may be incorrect.", 'warning')
        previous_balance = 0 # Default to 0 if no BBF is found
    final_data = []
    for tx in parsed_data:
        debit, credit = "", ""
        if "Bal Brought Forward" in tx['description']:
            final_data.append({**tx, 'debit': '', 'credit': ''}); continue
        tolerance = 0.01
        if previous_balance != 0 and abs((previous_balance - tx['amount']) - tx['balance']) < tolerance:
            debit = f"{tx['amount']:.2f}"
        elif abs((previous_balance + tx['amount']) - tx['balance']) < tolerance:
            credit = f"{tx['amount']:.2f}"
        elif tx['amount'] == 0.00:
            debit = "0.00"
        final_data.append({**tx, 'debit': debit, 'credit': credit}); previous_balance = tx['balance']
    return final_data

# --- Intelligent Categorization and Grouping ---

def categorize_transactions(transactions: list[dict], custom_rules: dict) -> list[dict]:
    """Applies comprehensive categorization with noise removal and case-insensitivity."""
    effective_date_pattern = re.compile(r'\(effective\s*\d{1,2}/\d{2}/\d{4}\s*\)', re.IGNORECASE)
    
    main_category_rules = {
        "Bank Charges": ["admin charge","Admin Charge", "monthly fee", "management fee", "notific fee", "archive stmt enq", "card replacement"],
        "Card Purchase": ["pos purchase", "overseas purchase", "Pos Purchase", "pospurchase"],
        "Cash Operation": ["cash acceptor dep", "cash deposit", "cash withdrawal", "atm withdrawal"],
        "Digital Transfer": ["digital transf", "eft", "interbank"],
        "Digital Payment": ["digital payment","Digital Payment"],
        "Credit Transfer": ["acb credit", "cr settlement"],
        "Debit Order": ["debit order", "d/o"],
        "Voucher": ["digital vouchers grp"]
    }
    subcategory_rules = {
        "Groceries": ["checkers", "pick n pay", "pnp", "woolworths", "shoprite", "spar", "food lovers"],
        "Household": ["dis-chem", "clicks", "game", "builders"],
        "Restaurants & Takeaways": ["steers", "kfc", "nandos", "mcdonalds", "kauai", "wimpy", "milky lane"],
        "Food Delivery": ["uber eats", "mr d food", "ubereats"],
        "Coffee Shops": ["starbucks", "vida e", "seattle coffee", "thecafe23"],
        "Subscriptions & Media": ["netflix", "spotify", "showmax", "dstv", "youtube premium", "apple.com/bill"],
        "Fuel": ["sasol", "shell", "bp", "total", "engen"],
        "Ride Hailing": ["uber", "bolt"],
        "Vehicle Maintenance": ["supa quick", "tiger wheel", "bosch"],
        "Public Transport": ["gautrain"],
        "Tolls & Roads": ["sanral", "bakwena", "rtmc"],
        "General Shopping": ["takealo", "superbalist", "amazon", "h&m"],
        "Electronics": ["incredible connection", "istore"],
        "Books & Stationery": ["pna", "postnet"],
        "Gaming": ["steamgames", "playstation", "xbox"],
        "Phone & Airtime": ["airtime", "vodacom", "mtn", "cell c", "telkom"],
        "Utilities": ["eskom", "city power", "city of jhb", "city of cpt", "rand water"],
        "Medical": ["dischem", "clicks", "momentum", "discovery", "pathcare", "lancet"],
        "Investments": ["easyequities", "absa bank bit", "luno", "absa bank crypto", "absa bank mine"],
        "Income": ["cashfocus", "salary", "dad", "mom"],
        "Nsfas": ["ukzn_fin aid"]
    }
    
    final_data = []
    for tx in transactions:
        clean_description = re.sub(effective_date_pattern, '', tx['description']).strip()
        tx_desc_lower = clean_description.lower()
        tx['description'] = clean_description
        sub_cat_assigned = False

        if "bal brought forward" in tx_desc_lower:
            tx['Category'], tx['Sub-category'] = "Balance", "Opening Balance"
            final_data.append(tx); continue

        for keyword, sub_cat in custom_rules.items():
            if keyword.lower() in tx_desc_lower:
                tx['Sub-category'] = sub_cat; sub_cat_assigned = True; break
        
        if not sub_cat_assigned:
            for sub_cat, keywords in subcategory_rules.items():
                if any(k.lower() in tx_desc_lower for k in keywords):
                    tx['Sub-category'] = sub_cat; sub_cat_assigned = True; break

        assigned_main_category = "Other"
        for main_cat, keywords in main_category_rules.items():
            if any(k.lower() in tx_desc_lower for k in keywords):
                assigned_main_category = main_cat; break
        tx['Category'] = assigned_main_category

        if assigned_main_category in ["Digital Transfer", "Credit Transfer"]:
            if tx.get('debit'): tx['Sub-category'] = "Transfer Out"
            elif tx.get('credit'): tx['Sub-category'] = "Transfer In"
            sub_cat_assigned = True

        if not sub_cat_assigned:
            tx['Sub-category'] = 'Uncategorized'
        final_data.append(tx)
    return final_data

def generate_grouping_key(description: str) -> str:
    """Creates a 'smart' key for grouping similar transactions."""
    key = description.lower()
    noise_words = [
        'pos purchase settlement', 'pos purchase', 'pospurchase', 'card no', 'settlement', 
        'durba', 'durban', 'cape town', 'johannesburg', 'pretoria', 's2s', 'overseas purchase', 
        'digital payment', 'payment', 'eft'
    ]
    for word in noise_words: key = key.replace(word, '')
    key = re.sub(r'\d', '', key) # Remove all digits, not just sequences
    key = key.replace('*', ' ').replace('#', ' ').replace('_', ' ').replace('\'', ' ')
    return " ".join(key.split()).strip()

# --- Flask Routes ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process_pdf():
    uploaded_files = request.files.getlist('pdf_file')
    if not uploaded_files or all(f.filename == '' for f in uploaded_files):
        flash('No files selected.', 'error'); return redirect(url_for('index'))
    all_transactions, bbf_found = [], False
    custom_rules = load_custom_rules()
    for file in uploaded_files:
        if file and file.filename.lower().endswith('.pdf'):
            filename = secure_filename(file.filename)
            pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(pdf_path)
            try:
                all_lines = get_all_lines_from_pdf(pdf_path)
                transaction_blocks = group_transactions_from_lines(all_lines)
                parsed_transactions = parse_and_sort_transactions(transaction_blocks)
                categorized = categorize_transactions(parsed_transactions, custom_rules)
                for tx in categorized:
                    if "Bal Brought Forward" in tx['description']:
                        if not bbf_found: all_transactions.append(tx); bbf_found = True
                    else: all_transactions.append(tx)
                flash(f'Successfully processed "{filename}".', 'success')
            except Exception as e:
                flash(f'An error occurred while processing "{filename}": {e}', 'error')
            finally:
                if os.path.exists(pdf_path): os.remove(pdf_path)
    if not all_transactions:
        flash('Failed to extract any transactions.', 'error'); return redirect(url_for('index'))
    all_transactions.sort(key=lambda x: x['date_obj'])
    for tx in all_transactions: tx['Account'] = 'Checking'
    fully_categorized = [tx for tx in all_transactions if tx.get('Sub-category') != 'Uncategorized']
    to_review = [tx for tx in all_transactions if tx.get('Sub-category') == 'Uncategorized']
    session['categorized_data'] = fully_categorized
    if to_review:
        session['review_data'] = to_review
        return redirect(url_for('review_page'))
    else:
        session['processed_data'] = fully_categorized
        return redirect(url_for('show_results'))

@app.route('/review')
def review_page():
    review_data = session.get('review_data')
    if not review_data:
        flash('No items to review.', 'info'); return redirect(url_for('index'))
    grouped_for_review = {}
    for tx in review_data:
        group_key = generate_grouping_key(tx['description'])
        if not group_key: continue
        if group_key not in grouped_for_review:
            grouped_for_review[group_key] = {'count': 0, 'sample_tx': tx}
        grouped_for_review[group_key]['count'] += 1
    custom_rules = load_custom_rules()
    subcategory_rules = {"Groceries": [], "Household": [], "Restaurants & Takeaways": [], "Food Delivery": [], "Coffee Shops": [], "Subscriptions & Media": [], "Fuel": [], "Ride Hailing": [], "Vehicle Maintenance": [], "Public Transport": [], "Tolls & Roads": [], "General Shopping": [], "Electronics": [], "Books & Stationery": [], "Gaming": [], "Phone & Airtime": [], "Utilities": [], "Medical": [], "Investments": [], "Income": [], "Nsfas": []}
    all_subcategories = sorted(list(set(subcategory_rules.keys()).union(set(custom_rules.values()))))
    return render_template('review.html', grouped_items=grouped_for_review, all_subcategories=all_subcategories)

@app.route('/update_rules', methods=['POST'])
def update_rules():
    custom_rules = load_custom_rules()
    review_data = session.get('review_data', [])
    categorized_data = session.get('categorized_data', [])
    new_rules_made = False
    group_keys = request.form.getlist('group_key')
    for i, key in enumerate(group_keys):
        selected_cat = request.form.get(f'cat_{i}')
        new_cat = request.form.get(f'new_cat_{i}', '').strip()
        final_cat = new_cat if new_cat else selected_cat
        if final_cat and final_cat != 'skip':
            for tx in review_data:
                if generate_grouping_key(tx['description']) == key:
                    tx['Sub-category'] = final_cat
            if key not in custom_rules:
                custom_rules[key] = final_cat; new_rules_made = True
    if new_rules_made:
        save_custom_rules(custom_rules); flash('New intelligent categorization rules have been saved!', 'success')
    final_data = categorized_data + review_data
    final_data.sort(key=lambda x: x['date_obj'])
    session['processed_data'] = final_data
    session.pop('review_data', None); session.pop('categorized_data', None)
    return redirect(url_for('show_results'))

@app.route('/results')
def show_results():
    processed_data = session.get('processed_data')
    if not processed_data:
        flash('No data to display. Please process a file first.', 'error'); return redirect(url_for('index'))
    chart_data = {}
    for tx in processed_data:
        debit = float(tx.get('debit') or 0)
        sub_category = tx.get('Sub-category', 'Uncategorized')
        if debit > 0 and sub_category not in ['Opening Balance', 'Transfer In']:
            chart_data[sub_category] = chart_data.get(sub_category, 0) + debit
    sorted_chart_data = dict(sorted(chart_data.items(), key=lambda item: item[1], reverse=True))
    chart_labels = list(sorted_chart_data.keys())
    chart_values = list(sorted_chart_data.values())
    total_debit = sum(float(tx.get('debit') or 0) for tx in processed_data)
    total_credit = sum(float(tx.get('credit') or 0) for tx in processed_data)
    table_headers = ['Date', 'Category', 'Description', 'Debit', 'Credit', 'Sub-category']
    return render_template('result.html', transactions=processed_data, headers=table_headers, total_debit=total_debit, total_credit=total_credit, chart_labels=chart_labels, chart_values=chart_values)

@app.route('/download')
def download_file():
    processed_data = session.get('processed_data')
    original_filename = session.get('original_filename', 'statement.pdf')
    if not processed_data:
        flash('No data available to download. Session may have expired.', 'error'); return redirect(url_for('index'))
    df = pd.DataFrame(processed_data)
    output_columns = ['Account', 'date', 'Category', 'description', 'debit', 'credit', 'Sub-category']
    if 'Account' not in df.columns: df['Account'] = 'Checking'
    df_to_export = df.drop(columns=['date_obj'], errors='ignore')
    output_df = df_to_export.reindex(columns=output_columns).rename(columns={'date': 'Date', 'description': 'Description', 'debit': 'Debit', 'credit': 'Credit'})
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        output_df.to_excel(writer, index=False, sheet_name='Transactions')
    output.seek(0)
    session.pop('processed_data', None); session.pop('original_filename', None)
    return send_file(output, download_name=f"categorized_{original_filename.replace('.pdf', '.xlsx')}", as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/clear')
def clear_session():
    session.clear()
    flash('Your session has been cleared. You can start fresh.', 'success')
    return redirect(url_for('index'))

if __name__ == "__main__":
    app.run(debug=True)