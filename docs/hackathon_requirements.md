# Architecture 
 Direct Agent Extension (Claude Code / OpenClaw) --- Extend Protocol SIFT's existing agent loop. Better prompt engineering, smarter tool sequencing, self-correction routines, accuracy validation. This is the on-ramp for most participants and the fastest path to a working submission. OpenClaw's extensible architecture also makes it a natural fit for building custom MCP tool wrappers directly into the tool chain.

 # Purpose 
 What to Build

One goal: Make Protocol SIFT a fully autonomous incident response agent.

Your submission must improve how Protocol SIFT processes case data --- any case data. Disk images, memory captures, remote endpoints via MCP, log files, network captures. The data type doesn't define the track. The quality of autonomous execution does.

Teach the agent how a senior analyst thinks. How they sequence their approach. How they recognize when something doesn't add up. How they adjust.

# Required Features
What to Submit

All eight components required. Missing any one means elimination.

1.  Code Repository --- GitHub (public). Open-source license (MIT or Apache 2.0).

2.  Demo Video (5 min max) --- Screencast of live terminal execution with audio narration. Show the agent working against real case data, including at least one self-correction sequence.

3.  Architecture Diagram --- How components connect: the agent, SIFT tools, MCP servers, data sources, output pipeline. Your diagram must identify which architectural pattern you're using and document where security boundaries are enforced. Prompt-based guardrails and architectural guardrails must be clearly distinguished. Judges need to understand your system and its trust boundaries at a glance.

4.  Written Project Description --- Devpost project story format: What it does, How you built it, Challenges, What you learned, What's next. Be specific about design decisions, tradeoffs, and which qualities of autonomous execution your submission addresses.

5.  Dataset Documentation --- What the agent was tested against, source of data, and what it found. Reproducibility starts here.

6.  Accuracy Report --- Self-assessment of findings accuracy. False positives, missed artifacts, hallucinated claims. Include a section documenting your evidence integrity approach: how does your architecture prevent original data from being modified? If you're using prompt-based restrictions rather than architectural enforcement, document what happens when the model ignores the restriction. Did you test for spoliation? (If you found failure modes, document them. That's signal, not weakness.)

7.  Try-It-Out Instructions --- Live deployment URL or step-by-step instructions for judges to run your agent locally on the downloadable SIFT workstation. If local setup requires specific tools or dependencies, document them clearly in the README.

8.  Agent Execution Logs --- Structured logs showing the full agent communication and tool execution sequence. For multi-agent submissions: agent-to-agent message logs with timestamps. For single-agent submissions: tool execution logs with timestamps and token usage. For persistent loop submissions: iteration-over-iteration traces showing how the agent's approach changed. Judges must be able to trace any finding back to the specific tool execution that produced it.

# Nice to Have 
Screencast video (2-5 min duration ) that shows the solution in action 



# Project Constraints 
Solution must be submitted by June 15 2026 

2-person Team
- All members are AI novices
- one is a Software Developer (backend specialist)
- one is a Network Engineer / Security Automation expert 

All components must live in AWS (preferably free-tier)

Python 

Budget $150 
- this needs to cover 6 weeks of development, testing and demos

# Team Motivator

The solution should be highly portable, low friction and easy to share with others. The team is more interested in learning and gaining hands-on experience than winning (although we would not shun an opportunity to be competitive!)



