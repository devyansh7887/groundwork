import os, re
files = ['synthesizer.py', 'verifier.py', 'diagram_agent.py', 'onboarding_agent.py', 'contribution_drafter.py']
for f in files:
    with open(f, 'r', encoding='utf-8') as file:
        content = file.read()
    
    pattern = r'if GROQ_API_KEY and "dummy" not in GROQ_API_KEY:\s*self\.llm = ChatGroq\(model="llama-3\.3-70b-versatile", groq_api_key=GROQ_API_KEY, temperature=([0-9.]+)\)\s*else:\s*if GROQ_API_KEY and "dummy" not in GROQ_API_KEY:\s*self\.llm = ChatGroq\(.*?max_retries=10\)\s*else:\s*self\.llm = ChatGoogleGenerativeAI\((.*?)\)'
    
    def fix_block(m):
        temp = m.group(1)
        inner = m.group(2)
        return f'''if GROQ_API_KEY and "dummy" not in GROQ_API_KEY:
            self.llm = ChatGroq(model="llama-3.3-70b-versatile", groq_api_key=GROQ_API_KEY, temperature={temp}, max_retries=10)
        else:
            self.llm = ChatGoogleGenerativeAI({inner})'''
            
    new_content = re.sub(pattern, fix_block, content, flags=re.DOTALL)
    
    with open(f, 'w', encoding='utf-8') as file:
        file.write(new_content)
print('Fixed!')
