import asyncio
import json
from pipeline import Pipeline

async def main():
    repo = 'https://github.com/lukeed/kleur'
    print(f'Running pipeline on {repo}...')
    pipeline = Pipeline()
    
    state = await pipeline.run(repo)
    
    print('\n--- Cartographer Graph Output (Sample) ---')
    print(json.dumps(state['graph']['nodes'][:2], indent=2))
    
    print('\n--- Synthesizer Claims Output ---')
    print(json.dumps(state['claims'][:2], indent=2))
    
    print('\n--- Diagram Agent Output ---')
    print(state['mermaid_diagram'][:200])
    
if __name__ == '__main__':
    asyncio.run(main())
