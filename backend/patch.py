import os
import re

files = ["synthesizer.py", "verifier.py", "diagram_agent.py", "onboarding_agent.py", "contribution_drafter.py"]

for f in files:
    with open(f, "r", encoding="utf-8") as file:
        content = file.read()
    
    # Add ChatGroq import
    if "from langchain_groq import ChatGroq" not in content:
        content = content.replace("from langchain_google_genai import ChatGoogleGenerativeAI", "from langchain_google_genai import ChatGoogleGenerativeAI\nfrom langchain_groq import ChatGroq")
        
    # Add GROQ_API_KEY
    if "GROQ_API_KEY" not in content:
        content = content.replace("from config import GEMINI_API_KEY", "from config import GEMINI_API_KEY, GROQ_API_KEY")
    
    pattern = r'self\.llm\s*=\s*ChatGoogleGenerativeAI\((.*?)\)'
    
    def repl(m):
        inner = m.group(1)
        temp = "0.0"
        if "temperature=" in inner:
            temp_match = re.search(r'temperature=([0-9.]+)', inner)
            if temp_match:
                temp = temp_match.group(1)
                
        # Fix indentation dynamically
        return f'''if GROQ_API_KEY:
            self.llm = ChatGroq(model="llama-3.3-70b-versatile", groq_api_key=GROQ_API_KEY, temperature={temp}, max_retries=10)
        else:
            self.llm = ChatGoogleGenerativeAI({inner})'''
            
    content = re.sub(pattern, repl, content, flags=re.DOTALL)
    
    with open(f, "w", encoding="utf-8") as file:
        file.write(content)

print("Patch applied successfully.")
