# Interactive coaching session `week1` — 2026-11-01

Target opportunity: **AI Engineer Intern, Agent Platform (Summer 2027)** — Northbay Agents (sample). Grader: offline (heuristic mode); coding answers run against unit tests.

## Question 1 of 6 · Evaluation & observability · concept · difficulty 2/3

**Coach:** How would you evaluate an LLM agent before shipping it, and how would you keep evaluating it after launch?

**Student:** I would create a test set of example tasks with the expected result and run the agent on all of them to get an accuracy number. For open-ended answers I would use an LLM as a judge with a rubric so it grades consistently. I'd also do some manual review of a sample.

**Coach evaluation:** 67%. Covered: a golden test set; LLM-as-a-judge with a rubric; human review; task success metrics. Missing: regression tests in CI; online monitoring and A/B tests.

**Reference answer:** Before launch: a golden dataset of realistic tasks with expected outcomes, measured by task success, code-based checks where possible, and LLM-as-a-judge with a rubric calibrated against human labels; run it in CI as a regression gate. After launch: trace every run, sample production traffic for online scoring, A/B test changes, and feed failures back into the test set.

## Follow-up challenge · Evaluation & observability · concept · difficulty 2/3

**Coach:** Give one metric for the agent's *trajectory* (how it got there), not just its final answer.

**Student:** For the trajectory I would look at the tool calls: did it pick the right tool, and how many steps it took compared to the minimum needed. Redundant or repeated calls mean wasted cost and latency even if the final answer is right.

**Coach evaluation:** 100%. Covered: evaluate the tool-call trajectory; step efficiency / wrong-tool rate.

## Question 2 of 6 · MLOps & deployment · design · difficulty 2/3

**Coach:** How would you deploy and monitor an LLM-powered API in production?

**Student:** I would put it in a Docker container and deploy it, then add logging so I can see errors.

**Coach evaluation:** 33%. Covered: containerized deployment; logging and tracing. Missing: latency, cost and token tracking; rate limits, retries and fallbacks; quality evaluation and drift; versioning, canaries and rollback. Answer is very short; interviewers expect reasoning, not keywords.

**Reference answer:** Containerize the service, version prompts and models, roll out with canaries and fast rollback; track latency, error rate, token usage and cost per request; trace every call; handle rate limits with retries, timeouts and model fallbacks; continuously sample outputs for quality evaluation and user feedback.

## Follow-up challenge · MLOps & deployment · design · difficulty 2/3

**Coach:** Your provider starts returning 429 rate-limit errors during a traffic spike. Walk me through what your service should do in the next 60 seconds.

**Student:** I don't know

**Coach evaluation:** 0%. No worries — not knowing is useful signal. This gap is now in your study plan; the resources in your report cover it.

## Question 3 of 6 · Agentic AI & orchestration · coding · difficulty 3/3

**Coach:** Agent planners often run tasks as a DAG. Write `topo_order(deps)` where `deps` maps each task to the list of tasks it depends on. Return an order in which every task appears after its dependencies, choosing the alphabetically smallest available task at each step. Return `[]` if there is a cycle. Tasks that appear only as dependencies are tasks too.

**Student:**

```python
```python
import heapq

def topo_order(deps):
    nodes = set(deps)
    indeg = {n: 0 for n in nodes}
    children = {n: [] for n in nodes}
    for task, ds in deps.items():
        for d in ds:
            indeg[task] += 1
            children[d].append(task)
    ready = [n for n in nodes if indeg[n] == 0]
    heapq.heapify(ready)
    order = []
    while ready:
        n = heapq.heappop(ready)
        order.append(n)
        for c in children[n]:
            indeg[c] -= 1
            if indeg[c] == 0:
                heapq.heappush(ready, c)
    return order
```
```

**Coach evaluation:** 80%. 4/5 tests passed. First failure on input [{'c': ['a', 'b']}]: KeyError: 'a'.

## Question 4 of 6 · Agentic AI & orchestration · concept · difficulty 2/3

**Coach:** In LangGraph, explain state, nodes, edges and checkpointers. Why does checkpointing matter for a human-in-the-loop agent?

**Student:** State is a shared TypedDict that every node reads and updates. Nodes are just Python functions, and edges connect them, including conditional edges that route based on the state. A checkpointer saves the state after each step so if the graph hits an interrupt it can pause, wait for a human to approve, and then resume from the same point later.

**Coach evaluation:** 100%. Covered: state as a shared typed object; nodes as functions; edges and conditional routing; checkpointers persist state; pause/resume for human approval.

## Question 5 of 6 · LLM fundamentals · concept · difficulty 2/3

**Coach:** What does temperature control during decoding, and when would you set it low versus high?

**Student:** Temperature controls randomness. Low temperature gives more consistent answers so I'd use it for extracting data. Higher temperature is more creative.

**Coach evaluation:** 75%. Covered: temperature shapes the sampling distribution; low for deterministic tasks; high for diverse output. Missing: it rescales logits before softmax.

## Question 6 of 6 · Behavioral & communication · behavioral · difficulty 2/3

**Coach:** Describe a disagreement with a teammate about a technical decision. How did you resolve it?

**Student:** In my distributed systems class project, my teammate wanted to use Kafka and I thought a simple Redis queue was enough for our load. I listened to his concern, which was about losing messages, and suggested we prototype both and benchmark them with our expected traffic. The benchmark showed Redis was fine but his durability point was real, so we agreed on Redis with persistence turned on. We delivered on time and I learned to move disagreements to data quickly.

**Coach evaluation:** 100%. Covered: understanding their view; using evidence; reaching a decision; outcome and lesson.

## Session outcome

Readiness for this target: **76%**. Full report: `career_readiness_2026-11-01_week1.md`.
