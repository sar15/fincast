import os
import json
import io
import pandas as pd
from pydantic import BaseModel, Field
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.output_parsers import PydanticOutputParser
from typing import List

class FinancialMonth(BaseModel):
    month: str = Field(description="The month and year, formatted as YYYY-MM")
    revenue: float = Field(description="Total revenue for the month")
    cogs: float = Field(description="Cost of Goods Sold for the month. Always positive absolute value.")
    opex: float = Field(description="Operating Expenses for the month. Always positive absolute value.")
    payroll: float = Field(description="Salary, wages, PF, ESI expenses. Always positive.", default=0)
    debt_service: float = Field(description="Loan EMI, interest payments. Always positive.", default=0)
    capex: float = Field(description="Capital expenditure, fixed asset purchases. Always positive.", default=0)
    ar_balance: float = Field(description="Accounts Receivable ending balance for the month", default=0)
    ap_balance: float = Field(description="Accounts Payable ending balance for the month", default=0)
    cash_balance: float = Field(description="Ending actual cash balance for the month", default=0)
    line_items: dict[str, float] = Field(description="A dictionary of all granular line items found (e.g., 'Marketing', 'Rent', 'Software', 'Travel'). Maintain exact original category names and positive absolute float values.", default_factory=dict)

class ExtractedFinancials(BaseModel):
    data: List[FinancialMonth] = Field(description="Chronological list of extracted monthly financials")

# Make sure GOOGLE_API_KEY is in your environment
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)

parser = PydanticOutputParser(pydantic_object=ExtractedFinancials)

prompt = PromptTemplate(
    template="""You are a highly expert forensic accountant AI specializing in Indian SME financials.
Extract monthly financial metrics from the messy spreadsheet data provided.

For EACH month, extract:
- revenue: Total revenue/sales/turnover/income/receipts
- cogs: Cost of goods sold / direct costs / purchases / material costs
- opex: Operating expenses / indirect expenses / admin / overhead
- payroll: Salaries, wages, PF, ESI, employee costs
- debt_service: Loan EMI, interest payments, borrowings repayment
- capex: Capital expenditure, fixed asset purchases, equipment
- ar_balance: Accounts receivable / debtors / sundry debtors balance
- ap_balance: Accounts payable / creditors / sundry creditors balance
- cash_balance: Cash and bank balance at end of month
- line_items: Dictionary of ALL granular expense/revenue categories found

RULES:
1. All monetary values must be POSITIVE absolute values (no negatives)
2. If exact values are missing, deduce from context or set to 0.0
3. Revenue should not be zero unless the data explicitly shows zero
4. Ensure chronological order (oldest to newest month)
5. Handle Indian currency symbols (₹) and number formats (lakhs/crores)

Format instructions:
{format_instructions}

Raw Messy Spreadsheet Data:
{messy_data}
""",
    input_variables=["messy_data"],
    partial_variables={"format_instructions": parser.get_format_instructions()},
)

chain = prompt | llm | parser

async def parse_financials(file_bytes: bytes, filename: str) -> ExtractedFinancials:
    """Takes a messy file, reads primitive text, uses Gemini to normalize perfectly"""
    
    # Try reading as CSV or Excel
    try:
        if filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(file_bytes))
        else:
            df = pd.read_excel(io.BytesIO(file_bytes))
            
        # Convert df to a raw string format that the LLM can easily read
        # E.g., Markdown table or simple string
        messy_data = df.to_string()
        
        # In reality, this data might exceed standard context limits if it's huge, 
        # but Gemini 1.5 flash has a massive 1M token window, so dumping df.to_string() is fine.
        result = await chain.ainvoke({"messy_data": messy_data[:200000]}) # limit raw string size just in case
        
        # Sort chronologically just to be safe
        result.data.sort(key=lambda x: x.month)
        return result
        
    except Exception as e:
        print(f"Error parsing file: {e}")
        raise e
