# Absa-Bank-Statement-Converter
# PDF Bank Statement Processor 📄➡️📊

A web application designed to parse, categorize, and visualize financial transactions from PDF bank statements. This tool transforms the tedious task of manual data entry into an automated, interactive, and intelligent process, complete with a web-based GUI.

**Please Note:** This tool is currently optimized for **Absa Cheque Account** statements. Results may be inaccurate for other banks or account types.

---
## Screen shot
![Screenshot 2025-06-19 001219](https://github.com/user-attachments/assets/8bf75edb-850e-443b-a482-e92405d5aafd)


## Live Demo

You can try the live application here:
**https://absa-bank-statement-converter-cheque.onrender.com/**

*(Note: The free hosting tier may cause the app to "spin down" after 15 minutes of inactivity. The first visit after a spin-down may take up to 60 seconds to load.)*

## Key Features

*   **PDF Parsing**: Extracts all transaction data directly from one or more uploaded PDF bank statements.
*   **Intelligent Categorization**: Automatically assigns a main category and a sub-category to each transaction using a comprehensive set of built-in rules.
*   **Smart Learning System**: If a transaction is uncategorized, the app presents it in a grouped review page. Your choice is saved and automatically applied to all future transactions with a similar description.
*   **Smart Grouping**: The review page intelligently groups similar transactions (e.g., multiple purchases from the same store on different dates) so you only have to categorize them once.
*   **Interactive Data Visualization**: View a clean, interactive pie chart of your expense breakdown by category.
*   **Excel Export**: Download the fully processed and categorized data as a clean `.xlsx` file with a single click.
*   **Modern UI**: A responsive, user-friendly interface with drag-and-drop file upload and a modal-based chart view.

*   **Render**: For free, continuous deployment and hosting of the live web service.


## Future Improvements

*   **Support for Other Banks**: Expand the parsing and categorization logic to handle statements from other major banks (e.g., FNB, Standard Bank, Nedbank, Capitec).
*   **Persistent Custom Rules**: Integrate a lightweight database (like SQLite or a free-tier cloud database) to permanently store user-defined rules, even after the server restarts.
*   **More Chart Types**: Allow users to view their data as a bar chart (monthly spending) or a line chart (balance over time).
*   **User Accounts**: Add user authentication so that multiple users can have their own private, saved categorization rules.

## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details.
