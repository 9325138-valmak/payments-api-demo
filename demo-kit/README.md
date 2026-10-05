# Demo kit

Pre-sales material for the payments integration demo in this repository: the documents a solutions engineer or solutions consultant would use to take a prospect from first call to a working proof of concept.

The scenario is a fictional prospect, **Northwind Brokerage**, adding card deposits to its trading app. Every technical claim in these documents is backed by code in this repository and can be shown live.

| File | What it is | When it is used |
|---|---|---|
| [solution-brief.md](solution-brief.md) | One-page summary of the problem, the approach and the business value | Sent after the first call, or left behind after a demo |
| [discovery-guide.md](discovery-guide.md) | Questions to qualify the opportunity and uncover integration risks | First and second calls |
| [demo-script.md](demo-script.md) | A 5-minute live demo with talking points for each step | Technical demo to the prospect's team |
| [architecture.md](architecture.md) | Request and webhook flow diagrams | Technical deep dive, security review |
| [security-integration-faq.md](security-integration-faq.md) | Answers to the questions that appear in security questionnaires and RFPs | RFP / RFI responses, security review |
| [run_demo.sh](run_demo.sh) | Runs the whole demo end to end with one command | Before every demo, to check the environment |

## Run the demo

From the repository root, inside the virtual environment from the main [README](../README.md):

```bash
bash demo-kit/run_demo.sh
```

It starts the simulated provider and the service, then walks through a provider outage, a client retry, duplicate webhooks and a forged webhook. It takes about 10 seconds.

## Honest limits

This is a demo built against a simulated provider, not a production system. The [Limitations](../README.md#limitations) section of the main README lists what a production version would add. Saying this clearly in front of a prospect builds more trust than overselling.
