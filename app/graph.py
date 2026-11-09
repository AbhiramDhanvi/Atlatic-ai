"""Adapted from entbappy/ATLAS-Enterprise-AI's LangGraph workflow."""
import re
from typing import TypedDict, Any
from langgraph.graph import StateGraph, START, END
from app.backend import rpc
from app.models import embed, answer
from app.config import settings
from app.guardrails import check_input, check_output

class State(TypedDict, total=False):
    question: str
    principal: Any
    history: list
    passages: list
    sources: list
    answer: str
    status: str

def guard(s):
    return {'question': check_input(s['question'])}

def retrieve(s):
    prior = [x['content'] for x in s.get('history', []) if x['role'] == 'user']
    query = prior[-1] + '\nFollow-up: ' + s['question'] if prior else s['question']
    hits = rpc(s['principal'], 'match_chunks', {
        'query_embedding': embed(query), 'match_threshold': settings().min_relevance,
        'match_count': 5})
    sources = [{'index': i+1, 'chunk_id': h['id'], 'document_id': h['document_id'],
                'title': h['title'], 'page': h['page'], 'excerpt': h['content'][:400]}
               for i, h in enumerate(hits)]
    return {'passages': hits, 'sources': sources}

def generate(s):
    evidence = '\n\n'.join(f'[{i+1}] {h["title"]}, page {h["page"]}: {h["content"]}'
                            for i, h in enumerate(s['passages']))
    return {'answer': answer(s['question'], evidence, s.get('history', [])), 'status': 'answered'}

def validate(s):
    text = check_output(s['answer'])
    if text != s['answer']:
        return {'answer': text, 'status': 'guardrail_blocked', 'sources': []}
    cited = {int(n) for n in re.findall(r'\[(\d+)\]', text)}
    if not cited or not cited.issubset(set(range(1, len(s['sources'])+1))):
        return {'answer': 'I could not produce an answer with valid supporting citations. Please rephrase your question.',
                'status': 'citation_failed', 'sources': []}
    return {'answer': text}

def no_evidence(s):
    return {'answer': 'I could not find supporting evidence in your documents.',
            'sources': [], 'status': 'no_evidence'}

def make_graph():
    g = StateGraph(State)
    for name, fn in [('guard', guard), ('retrieve', retrieve), ('generate', generate),
                     ('validate', validate), ('no_evidence', no_evidence)]:
        g.add_node(name, fn)
    g.add_edge(START, 'guard')
    g.add_edge('guard', 'retrieve')
    g.add_conditional_edges('retrieve', lambda s: 'generate' if s['passages'] else 'no_evidence')
    g.add_edge('generate', 'validate')
    g.add_edge('validate', END)
    g.add_edge('no_evidence', END)
    return g.compile()

graph = make_graph()

def chat(p, question, history=None):
    return graph.invoke({'principal': p, 'question': question, 'history': history or []})
