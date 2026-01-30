import json

data = []

with open('./wpp-collector/messages.jsonl', 'r', encoding='utf-8') as f:    
    for line in f:
        data.append(json.loads(line))
        
    


