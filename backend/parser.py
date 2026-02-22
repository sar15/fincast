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
    ar_balance: float = Field(description="Accounts Receivable ending balance for the month")
    cash_balance: float = Field(description="Ending actual cash balance for the month")
    line_items: dict[str, float] = Field(description="A dictionary of all granular line items found (e.g., 'Marketing', 'Rent', 'Software', 'Travel'). Maintain exact original category names and positive absolute float values.", default_factory=dict)

class ExtractedFinancials(BaseModel):
    data: List[FinancialMonth] = Field(description="Chronological list of extracted monthly financials")

# Make sure GOOGLE_API_KEY is in your environment
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)

parser = PydanticOutputParser(pydantic_object=ExtractedFinancials)

prompt = PromptTemplate(
    template="""You are a highly expert forensic accountant AI. 
Extract out monthly financial metrics from the messy spreadsheet raw text provided by the user. 
Normalize all text to extract strictly the Revenue, COGS (Cost of Goods Sold), OpEx (Operating Expenses), A/R (Accounts Receivable) ending balance, and the Cash ending balance.
CRITICAL: You must ALSO extract all specific granular expense or revenue line items (e.g., 'Advertising', 'Salaries', 'Rent', 'Consulting') into the `line_items` dictionary. Do not miss any specific categories. 
If exact values are missing for smaller metrics like COGS or OpEx, try to deduce them or set to 0.0. Revenue and Cash shouldn't be zero unless explicitly 0.
Ensure chronological order (oldest to newest month).

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
