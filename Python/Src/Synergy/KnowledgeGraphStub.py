import os
from crewai.tools import BaseTool
from pydantic import BaseModel, Field, field_validator
try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

from typing import Union, Any

class KnowledgeQueryInput(BaseModel):
    query: Union[str, dict, Any] = Field(..., description="查询关键词，例如 '油温限制'。")

    @field_validator('query', mode='before')
    @classmethod
    def parse_query_payload(cls, v):
        if isinstance(v, dict):
            if 'description' in v: return str(v['description'])
            if 'value' in v: return str(v['value'])
            if 'query' in v: return str(v['query'])
            return str(v)
        return v

class RegulationRetrievalTool(BaseTool):
    """
    Knowledge Graph Stub for Regulation Retrieval.
    This was extracted from knowledge_tool.py.
    """
    name: str = "Local Standards Knowledge Base"
    description: str = "检索本地 PDF 行业标准。用于查找参数阈值、诊断依据。"
    args_schema: type[BaseModel] = KnowledgeQueryInput

    def _run(self, query: str) -> str:
        search_query = str(query)

        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            knowledge_dir = os.path.join(current_dir, '..', '..', '..', 'knowledge')
            knowledge_dir = os.path.normpath(knowledge_dir)

            if not os.path.exists(knowledge_dir):
                return f"Stub Default: Knowledge folder not found. Assuming no specific regulation context for '{search_query}'."

            if not PdfReader:
                return f"Stub Default: pypdf not installed, unable to parse PDF documents."

            results = []
            file_found = False

            for filename in os.listdir(knowledge_dir):
                if not filename.lower().endswith('.pdf'): continue
                file_found = True
                file_path = os.path.join(knowledge_dir, filename)
                try:
                    reader = PdfReader(file_path)
                    text = ""
                    for page in reader.pages:
                        text += page.extract_text() or ""
                    
                    paragraphs = text.split('\n')
                    for i, p in enumerate(paragraphs):
                        if search_query in p:
                            context = f"【来源: {filename}】...{p.strip()}..."
                            if i + 1 < len(paragraphs):
                                context += paragraphs[i + 1].strip()
                            results.append(context)
                except Exception as e:
                    pass

            if not file_found or not results:
                return f"Stub Default: No direct matches for '{search_query}'. Using general knowledge."

            return "\n\n".join(results[:3])

        except Exception as e:
            return f"Retrieval Stub Error: {str(e)}"
