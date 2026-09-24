September 2026

The biggest safety bug in Anchor was in what the verifier did when it didn't know a fact. Neither model could have fixed it.

I found it by accident. A full-time employee asked for 999 days of leave, with no manager approval, and Anchor said VALID. The policy had been written by GPT from a one-page HR document that says leave is capped at 30 days and extensions need a manager. GPT wrote the cap as a permission: "leave_days <= 30 means valid". The verifier approves a request when any permission applies and no prohibition does. "Full-time and over 20 hours" applied. So the cap never bound anything.

What bothered me more was the benchmark. Two of its hand-labelled cases were a 45-day and a 40-day request with no approval, and both were labelled VALID. The labels were computed by running Z3 on the gold facts, so the benchmark had learned the bug and was grading everything against it. Every "0 dangerous approvals" number measured before this fix was measured against a policy that couldn't produce one.

**Unknowns**

Fixing the one policy was easy. But the general problem is harder, and it's about unknown facts. A request that says nothing about approval doesn't mean approval is false. The old verifier skipped any rule that mentioned an unknown fact. That's fine for permissions and wrong for prohibitions: skip "over 30 days without approval is invalid" and the request sails through.

The fix is to let Z3 do what it's good at. For each rule, ask two questions given the facts you do know: can it fire, and must it fire? A prohibition that must fire denies. One that can't fire is irrelevant, so you don't pester the user about its facts. One that might fire is the interesting case, and the only honest answer is to ask.

So a 45-day request with approval unstated now gets "Did your manager approve this?" A 10-day request with approval unstated gets approved, because the prohibition can't fire.

There was a second leak of the same kind, and it took me a while to see. GPT sometimes puts a business rule in the policy's global constraints, e.g. "leave_days <= 30 OR has_manager_approval == true". Constraints get added to the solver as things that are true. So when approval is unknown, Z3 concludes it must be true, since otherwise the constraint would be false. The verifier was assuming the request complied. Now only ranges on a single number ("leave_days > 0") are assumed; everything else is checked like a prohibition.

I assumed the prompt fix would matter most. I rewrote the generator's instructions to say limits are prohibitions, added a check that flags permissions that never restrict anything, and had GPT repair them. Then I measured it, and it barely mattered.

I generated nine policies from the three source documents with the old generator and nine with the new one, and ran 54 probe requests through each with the old and new verifier. With the old verifier, 7 of 39 violations got approved from old-generator policies and 6 of 39 from new ones. With the new verifier, it was 0 either way. Why didn't the prompt help? Because gpt-6-luna already writes most limits as prohibitions. What no prompt can do is make the verifier treat an unstated fact correctly.[1]

The prompt did earn its keep somewhere else. Three-valued logic has a cost: a policy full of rare exceptions (a fault, overnight use, a repair) would ask about every one of them before approving an ordinary request. The old generator's policies did exactly that, blocking 3 of 15 legitimate probes. The new prompt tells GPT to give rare adverse conditions a default of false and to leave approvals with no default, so the verifier asks about the second kind and not the first. With the new generator, 0 of 15 legitimate probes were blocked.

**Reading requests**

The other half of the system reads a request and turns it into facts. There are two readers. Jev answers multiple-choice questions about the text in about 350 ms and says how sure it is. gpt-6-luna reads the whole thing in about 1.4 seconds.

Jev's failure mode is the multiple choice itself. Ask "is the employee full-time, part-time, or a contractor?" about someone who says they're an intern, and it will pick full-time, with 0.89 confidence. Ask whether a manager approved, when the text says a coworker did, and it says yes at 0.83. You can't threshold your way out of that, because the confidence is high. What worked was giving it honest exits: "a value that isn't one of these", "mentioned, but hedged or claimed by someone without the authority", "several different numbers". On the held-out set that took Jev alone from 3 dangerous approvals to 1, and from 82% to 86% correct.

GPT had a failure mode too, and it was ours. The extraction prompt told it "full-time employees: assume 40 hours a week unless stated otherwise." So it did. That's gone.

I expected more reasoning effort to help GPT read more carefully. It didn't. On the tune set, effort none got 97.3% of verdicts right, low 95.2%, medium 95.7%, high 93.6%, xhigh 93.1%. None was also the fastest, with a median of 1.4 seconds against about 2 seconds for the rest, and a 95th percentile of 1.8 seconds against 5.4 for high.

Why would more thinking make it worse? My guess is that extraction is reading, not reasoning, and extra thinking mostly finds ways to infer facts that weren't stated. But I'm not sure, and on the 51 held-out cases the efforts are within two cases of each other.

**Combining them**

So you have a reader that's fast and sometimes confidently wrong, and one that's four times slower and usually right. The obvious move is to use the fast one when it's sure and the slow one when it isn't. The trick is deciding what "isn't sure" means, and it turned out to mean two different things.

The first is when Jev would ask the user for a fact it wasn't confident was missing. If a required fact came back empty with confidence below 0.6, GPT reads the request. The second is approvals. An approval is the one outcome you can't take back, so if any fact behind a VALID has confidence below 0.95, GPT reads the request before it stands. At 0.9 one dangerous approval got through on the tune set. At 0.95 none did.

My first version merged the two readings fact by fact, keeping a value only when both agreed. That seemed safer. But it wasn't: it threw away correct facts whenever GPT left one blank, and GPT at effort none leaves things blank a lot. Just deferring to GPT's whole reading, when you've decided you need it, was simpler and 1.2 points more accurate, with no dangerous approvals either way. The one thing worth guarding against is GPT writing an amount of 0 when no amount was given, since a $0 refund passes "refunds under $100 are fine". A zero now counts only if the text says zero, none, or free.

The result, on 239 requests: 93.3% of verdicts right, no dangerous approvals, GPT called on 34% of them, a median of 366 ms, and 516 GPT tokens per request. GPT alone gets 96.2%, also with no dangerous approvals, at a median of 1,414 ms and 1,514 tokens. So the hybrid gives up about three points. None of it is a wrong approval. Of its 16 misses, 13 are questions where a decision was possible (5 of those are approvals held because the request also tried to instruct the system), and 3 are denials of requests that should have passed. In exchange you get a median four times faster, a third of the tokens, and about three times the throughput under the same rate limit.[2]

I picked those two cutoffs on 188 requests and wrote down the selection rule before looking at the other 51. On those 51 the hybrid got 92.2%, the same as GPT alone.

Is that a tie? Fifty-one is not many. One case is two points, so the honest summary is that the hybrid is somewhere near GPT's accuracy on unseen requests and I can't tell you exactly where. Then I ran the same 51 through the live API rather than the simulation, and got the same 92.2%, no dangerous approvals, and a median of 371 ms.

**Where it will still break**

The applications this is built for are the ones where a request arrives as prose and the decision has to follow a written rule: leave and expense requests, contract signing, equipment use, and more and more, an AI agent that wants to issue a refund or delete a customer's data. That last one is where the remaining problems matter most.

The worst is that text can claim anything. "Supervisor approved" in a chat is not approval, and no reader, however good, can tell whether it's true. So a request can now carry facts from a system of record, and those override whatever the text says. A variable can be marked as trusted only, which means it's never read from text at all. For an agent acting on customer accounts, approvals and identity checks should always be trusted only. If you use Anchor that way and skip this, you've built a system that grants refunds to anyone who types the right sentence.

The second is coverage. The operations policy says equipment must be logged out in a portal before use, and the benchmark's policy has no variable for that, so a request that skipped the portal is approved. And nothing in Anchor notices a requirement that's missing from the policy altogether. The grounding check catches invented rules, not forgotten ones. The new prompt asks GPT to cover every requirement, and in the probe runs it did, but that's nine policies.

The rest are smaller. Jev can still be confidently wrong above 0.95, and nothing checks that. "Three weeks" is 21 calendar days here, and a policy about working days would disagree. Z3's default context isn't thread-safe, which is fine because every route that touches it is async, and not fine the day someone makes one of them a plain def. Running with GPT alone turns off the Jev guards, so there's no injection flag. And I labelled every benchmark case myself, which is exactly how the 45-day case got labelled wrong in the first place.

That last one is worth a second look. The most useful thing the benchmark did was be wrong in a way I happened to notice.

**Notes**

[1] It also means the leak check fires on some correct policies. A permission like "up to 30 days is fine", next to "over 30 days with approval is fine", looks like a limit written backwards, but together they're right. Each flag costs one GPT repair call at setup. I haven't measured how often that repair rewrites a policy that was already correct.

[2] The throughput figure is arithmetic, not a measurement: at a gpt-6-luna limit of 200,000 tokens a minute, which is about 130 requests a minute at 1,514 tokens each and about 390 at 516. Jev has its own limits, which I didn't hit.

**Numbers**

All runs used gpt-6-luna and jev-latest (jev-1.13.0), on the corrected bench policies. Tune is the 140 E1 bench cases plus 48 messy requests; held-out is 51 messy requests written afterwards and used only to report, never to choose. "Dangerous" means VALID when the gold verdict is not VALID. Latency is the model call only; the live API row includes HTTP and the database write.

| Strategy | Tune | Held-out | All 239 | Dangerous | GPT calls | p50 | p95 | Mean | GPT tokens/req |
|---|---|---|---|---|---|---|---|---|---|
| Jev only | 89.9% | 86.3% | 89.1% | 2 | 0% | 348 ms | 407 ms | 370 ms | 0 |
| gpt-6-luna, effort none | 97.3% | 92.2% | 96.2% | 0 | 100% | 1,414 ms | 1,769 ms | 1,477 ms | 1,514 |
| gpt-6-luna, effort low (old default) | 95.2% | 94.1% | 95.0% | 0 | 100% | 1,950 ms | 3,442 ms | 2,143 ms | 1,579 |
| gpt-6-luna, effort medium | 95.7% | 90.2% | 94.6% | 0 | 100% | 2,000 ms | 3,982 ms | 2,303 ms | 1,596 |
| gpt-6-luna, effort high | 93.6% | 94.1% | 93.7% | 0 | 100% | 2,148 ms | 5,431 ms | 2,634 ms | 1,618 |
| gpt-6-luna, effort xhigh | 93.1% | 90.2% | 92.5% | 0 | 100% | 2,025 ms | 5,100 ms | 2,550 ms | 1,637 |
| **Hybrid (shipped)** | **93.6%** | **92.2%** | **93.3%** | **0** | **34%** | **366 ms** | **2,003 ms** | **860 ms** | **516** |
| Hybrid, check every approval | 93.6% | 92.2% | 93.3% | 0 | 43% | 380 ms | 2,069 ms | 996 ms | 661 |
| Hybrid, escalate below 0.8 | 93.6% | 94.1% | 93.7% | 0 | 38% | 373 ms | 2,069 ms | 927 ms | 580 |
| Hybrid via live API (held-out only) | | 92.2% | | 0 | 31% | 371 ms | 2,899 ms | 1,034 ms | |

Shipped settings: `EXTRACTION_REASONING_EFFORT=none`, `HYBRID_ESCALATE_BELOW=0.6`, `HYBRID_CHECK_BELOW=0.95`, `HYBRID_FAIL_CLOSED=true`, `JEV_INJECTION_HOLDS_APPROVAL=true`. Selection rule, fixed before the held-out run: zero dangerous approvals on tune, tune accuracy within one point of the best such setting, then lowest mean latency. If GPT were started in parallel with Jev on every request, the hybrid's mean would drop from 860 ms to 741 ms, at the full GPT token cost.

Policy generation, 9 policies per generator (3 per source document), 18 probe requests across the three documents, each with a right answer that follows from its document:

| | Violations approved, old verifier | Violations approved, new verifier | Legitimate requests blocked, new verifier | Policies with leaky permissions | Mean generation time |
|---|---|---|---|---|---|
| Old generator | 7 / 39 | 0 / 39 | 3 / 15 | 7 / 9 | 26.2 s |
| New generator | 6 / 39 | 0 / 39 | 0 / 15 | 0 / 9 | 17.6 s |

Every leak under the old verifier came from two probes: 45 days with approval unstated, and a $400,000 contract with the CFO's sign-off unstated.

The benchmark harness, the 239 test requests, and the raw model outputs are kept out of this repository; the tables above are the record. The E1 to E10 exploration that came before them was run before the policy and verifier fixes, so its verdict numbers were graded against the buggy labels.
