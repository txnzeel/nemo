# Learning guide — Customer economics

Read the existing metric registry first. M7 keeps acquisition definitions and exact
INR paise accounting unchanged. All measures below are descriptive, not causal.

## 1. First-observed acquisition and monthly cohorts
1. Plain English: group buyers by the calendar month of their earliest paid order
   in the supplied history, with its observed session channel/campaign.
2. Business purpose: compare customers acquired at similar times and through observed
   channels without mixing visitors into the buyer denominator.
3. Example: a visitor first appears in January but pays in March. Their observed buyer
   cohort is March. A later paid-search purchase does not rewrite their original channel.
4. Formula: acquisition = earliest paid order per customer, ordered by paid_at then order_id.
   Cohort month = calendar month of that order in Asia/Kolkata.
5. Required data: canonical customer, session and paid-order identities/timestamps.
6. NEMO: reuse dbt purchase_rank = 1; attach that row's channel, campaign and paid flag.
   Do not invent first-ever acquisition or an attribution model.
7. Failure modes: left-censored history, identity changes and late earlier orders can
   alter observed acquisition. Channel credit does not show that advertising caused a purchase.
8. Interview: “My cohorts use first observed paid orders, explicitly bounded by supplied
   history. I do not count every visitor as an acquired customer.”

## 2. Calendar-month purchase retention
1. Plain English: among an original buyer cohort, what share placed a paid order in
   a particular later calendar month?
2. Business purpose: distinguish repeat purchasing patterns across acquisition groups.
3. Example: 10 March buyers, 3 of whom purchase in April, give month-1 retention of 3/10.
   A customer placing five April orders still counts once.
4. Formula: distinct cohort buyers purchasing in target month / original cohort size.
   Target month = acquisition month plus age_months.
5. Required data: first-observed cohort, order dates, distinct customer identities and
   the exclusive observation cutoff.
6. NEMO: generate an explicit cohort/age grid, retain zero for a completed month with
   no repeat purchases, and return null for a partial or future month. Month 0 is
   purchase activity in the acquisition month; it is not proof of repeat purchasing.
7. Failure modes: calendar months do not give equal days since each person's first order.
   Return after a skipped month is allowed. This is purchase retention, not subscription
   retention, survival probability, consecutive retention or a 30-day rolling measure.
8. Interview: “I distinguish true observed zeros from censored periods and keep the
   original cohort denominator, counting each active buyer once per month.”

Exercise: a May cohort has no June purchases and the snapshot ends June 15.
Is June retention zero? No: June is incomplete. Observed activity may be shown,
but the complete-period retention rate remains null.

## 3. Historical customer value
1. Plain English: receipts accumulated from observed paid orders, adjusted for observed
   merchandise refunds, through a declared cutoff.
2. Business purpose: describe realized commercial history without inventing future value.
3. Example: a buyer pays ₹1,000 then ₹500 and receives ₹200 in merchandise refunds.
   Historical net merchandise receipts are ₹1,300.
4. Formula: gross paid merchandise minus merchandise refunds observed through cutoff.
   Mean historical value = sum of net receipts / all cohort buyers.
5. Required data: paid orders, linked order items, refunds, complete refund coverage and
   exact money. Missing refund coverage is unknown, not an assumed zero.
6. NEMO: validate item/order reconciliation and refund bounds, aggregate refunds to orders
   before joining, then aggregate orders to customers and cohorts. Means retain exact
   numerator/denominator pairs. Customer value uses the full observed history.
7. Failure modes: later refunds can change the result; old cohorts have longer exposure.
   This is not predicted LTV, discounted cash flow, contribution, profit or a causal return.
8. Interview: “I report historical value with explicit coverage and follow-up, keeping
   forecasts and cost-based measures separate.”

## 4. Scoped order contribution before acquisition costs
1. Plain English: what remains from net merchandise receipts after the declared
   order-variable costs, before acquisition spending and fixed overhead.
2. Business purpose: distinguish sales volume from a supported, explicitly scoped
   contribution measure. It does not authorize a budget decision.
3. Example: ₹1,300 net merchandise receipts minus ₹700 known order-variable costs
   gives ₹600 scoped contribution. Unknown costs mean unknown contribution.
4. Formula: net merchandise receipts minus net COGS, fulfillment costs, payment fees,
   refund-handling costs and other declared order-variable costs.
5. Required data: explicit cost components per order, with return recoveries already
   reflected in net costs, complete refund coverage and the same cutoff/unit basis.
6. NEMO: every component must be known for an order's cost total to be usable.
   Missing rows or null components propagate unknown to that customer's/cohort's total.
   Zero is accepted only as an explicitly supplied value. Negative contribution is valid.
   The report names exclusions and source provenance; original M1 has no cost observations.
7. Failure modes: omitted costs, double-counted recoveries, fixed/variable classification,
   unmatched cutoffs and assumed values can mislead. This scope excludes acquisition
   costs and fixed overhead; it is not total company contribution or profit.
8. Interview: “I define the cost scope before calculating contribution and fail closed
   on missing components. I never relabel merchandise receipts as profit.”

Accounting foundation: contribution deducts variable costs before fixed expenses;
fixed expenses distinguish contribution from operating profit.
[OpenStax managerial accounting](https://openstax.org/books/principles-managerial-accounting/pages/3-1-explain-contribution-margin-and-calculate-contribution-margin-per-unit-contribution-margin-ratio-and-total-contribution-margin)
NEMO's deliberately narrower order-level scope and examples above are implementation
contracts, not a claim that every business uses these exact cost categories.

## Exercises and answers
- Should a visitor with no order lower buyer retention? No; they are outside the buyer cohort.
- Can one buyer be acquired again when their channel changes? Not under this contract.
- Is month-2 activity conditional on activity in month 1? No.
- Can refunds arriving in March adjust a January customer's historical value? Yes, through
  the current cutoff; they do not erase the historical January purchase activity.
- If all but one order have cost coverage, is cohort contribution complete? No.
- Does the synthetic cost demonstration estimate a real company's margins? No.
- Does positive scoped contribution imply profitable customer acquisition? No: acquisition
  costs, fixed costs and incremental effects remain outside this measure.

## Practice
Inspect the manual multi-month fixture in tests/test_economics.py. Calculate the first
cohort, a completed retention cell, an incomplete cell and net customer receipts by hand.
Then compare the refund-only and explicitly assumed-cost demonstration reports.
See customer-economics.md for contracts, commands and the worked dataset.
