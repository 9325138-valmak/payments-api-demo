# Discovery guide

Questions for the first and second calls with a prospect integrating payments. The goal is to understand the business problem, the technical environment and how a decision gets made, before any demo.

## 1. Business context

- What are you trying to launch or fix, and why now?
- How do clients fund accounts or pay today? What share fails, and what does a failure cost you (support time, lost deposits, churn)?
- Which payment methods and currencies matter in the first release? Which later?
- What volume do you expect at launch and in 12 months? Any daily peaks (market open, month end)?

## 2. Current pain

- When a payment request times out today, what does your system do? Has anyone been charged twice?
- How do you find out a payment succeeded: a webhook, polling, or a daily file?
- Have you ever credited an account twice, or missed a credit? How was it found and fixed?
- How long does reconciliation take each day, and who does it?

## 3. Technical environment

- What languages and frameworks does the team use? Where does it run (cloud, on premises)?
- Which provider is chosen, or still being evaluated? Is there a sandbox account?
- Who owns the integration: an in-house team, a vendor, or both? How many engineers?
- Is there an existing API gateway, message queue or event bus we should plug into?

## 4. Security and compliance

- Which regulators and frameworks apply (PCI DSS scope, local client-money rules, data residency)?
- Who runs the security review, and is there a standard questionnaire?
- What are the requirements for storing card data? (Aim: none stored, tokens only.)
- How long must payment and event records be kept, and in what form?

## 5. Decision process

- Who is involved in the decision, and who signs off: engineering, finance, compliance?
- What would a successful proof of concept need to show? Can we agree measurable criteria?
- What is the timeline, and what is driving it?
- What alternatives are you considering, including building it yourselves?

## After the call

Summarise in three lines: the business problem, the success criteria in the prospect's words, and the next step with a date. Send it the same day.
