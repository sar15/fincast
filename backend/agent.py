from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langchain_google_genai import ChatGoogleGenerativeAI
from typing import TypedDict, Annotated, Sequence
import operator
import os

# Define the state for the agent
class AgentState(TypedDict):
    messages: Annotated[Sequence[HumanMessage | SystemMessage], operator.add]
    context: dict

# Initialize Gemini Model via Langchain
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0,
    max_tokens=None,
    timeout=None,
    max_retries=2,
    # Make sure to set GOOGLE_API_KEY in your environment variables
)

# Define the core thinking node
def think_node(state: AgentState):
    messages = state["messages"]
    # Check if there's any financial context injected
    financial_context = state.get("context", {})
    
    # We can inject context into the prompt dynamically
    system_msg = SystemMessage(
        content=f"You are the FinCast AI Agent. You strictly analyze financial data for SMEs.\nContext: {financial_context}"
    )
    
    response = llm.invoke([system_msg] + messages)
    return {"messages": [response]}

# Build the LangGraph for the AI Agent Workflow
workflow = StateGraph(AgentState)
workflow.add_node("think", think_node)
workflow.add_edge(START, "think")
workflow.add_edge("think", END)

# Compile the Graph
fincast_agent = workflow.compile()

async def run_fincast_agent(user_query: str, financial_context: dict = None):
    """
    Utility function to run the FinCast AI agent asynchronously.
    """
    if financial_context is None:
        financial_context = {}
        
    initial_state = {
        "messages": [HumanMessage(content=user_query)],
        "context": financial_context
    }
    
    result = await fincast_agent.ainvoke(initial_state)
    return result["messages"][-1].content
