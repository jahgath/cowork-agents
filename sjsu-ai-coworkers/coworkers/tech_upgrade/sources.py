"""Authoritative technical sources.

`authority` (0..1) is an explicit editorial prior: primary engineering/research
blogs and peer-reviewed venues rank above aggregators. Feed URLs change over
time; `python -m coworkers.cli sources --check` reports any that fail so you
can update them here.
"""

SOURCES = [
    # org, display name, kind, url, authority
    {"org": "OpenAI", "name": "OpenAI News", "kind": "rss", "url": "https://openai.com/news/rss.xml", "authority": 0.95},
    {"org": "Anthropic", "name": "Anthropic Engineering", "kind": "html",
     "url": "https://www.anthropic.com/engineering", "authority": 0.95, "link_prefix": "/engineering/"},
    {"org": "Anthropic", "name": "Anthropic News", "kind": "html",
     "url": "https://www.anthropic.com/news", "authority": 0.9, "link_prefix": "/news/"},
    {"org": "Google", "name": "Google Research Blog", "kind": "rss", "url": "https://research.google/blog/rss/", "authority": 0.95},
    {"org": "Google", "name": "Google AI Blog", "kind": "rss", "url": "https://blog.google/technology/ai/rss/", "authority": 0.85},
    {"org": "Microsoft", "name": "Microsoft Research Blog", "kind": "rss", "url": "https://www.microsoft.com/en-us/research/feed/", "authority": 0.9},
    {"org": "AWS", "name": "AWS Machine Learning Blog", "kind": "rss", "url": "https://aws.amazon.com/blogs/machine-learning/feed/", "authority": 0.85},
    {"org": "IBM", "name": "IBM Research Blog", "kind": "html", "url": "https://research.ibm.com/blog", "authority": 0.85, "link_prefix": "/blog/"},
    {"org": "LangChain", "name": "LangChain Blog", "kind": "rss", "url": "https://blog.langchain.com/rss/", "authority": 0.8},
    {"org": "GitHub", "name": "GitHub Engineering Blog", "kind": "rss", "url": "https://github.blog/engineering/feed/", "authority": 0.85},
    {"org": "Hugging Face", "name": "Hugging Face Blog", "kind": "rss", "url": "https://huggingface.co/blog/feed.xml", "authority": 0.8},
    {"org": "NVIDIA", "name": "NVIDIA Technical Blog", "kind": "rss", "url": "https://developer.nvidia.com/blog/feed", "authority": 0.8},
    {"org": "IEEE", "name": "IEEE Spectrum (AI)", "kind": "rss",
     "url": "https://spectrum.ieee.org/feeds/topic/artificial-intelligence.rss", "authority": 0.85},
    {"org": "ACM", "name": "Communications of the ACM", "kind": "rss", "url": "https://cacm.acm.org/feed/", "authority": 0.9},
    {"org": "arXiv", "name": "arXiv (cs.AI / cs.CL / cs.LG)", "kind": "arxiv",
     "url": "http://export.arxiv.org/api/query", "authority": 0.75},
]

AUTHORITATIVE_ORGS = {s["org"] for s in SOURCES}
