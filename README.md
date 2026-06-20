# tollgate

> **Note to self before publishing:** this draft is mine to rewrite in
> my own voice before it goes live. It's structurally what I want —
> real anchor scenario first, then the gap, then what the tool does,
> then honest limits — but the sentences are Claude's, not mine. Read
> it once, then rewrite every paragraph the way I'd actually say it
> out loud to another architect over coffee. Don't ship this draft.

## The five-minute version

If you've ever had a wire transfer get rejected for a reason that
made no sense given that it "passed validation," you already know the
problem this solves.

Picture a payment integration team that just finished converting their
outbound payment file generator from the old MT103 format to pacs.008.
Everything passes the XSD. Every test in their CI suite is green. Then
it hits a real clearing network and gets bounced — not because the XML
is malformed, but because of something the schema was never built to
catch: a German customer's name with a "ü" in it, sitting in a field
that's perfectly valid XML and perfectly invalid on the wire, because
SWIFT's network layer restricts the character set independently of
what the XSD permits. Nobody on that team is wrong to be confused.
The schema said yes. The network said no. There's no single tool
that tells you about that gap before you submit.

Tollgate is that tool, for one message type, with a short and honest
list of gaps it covers.

## Why now, specifically

ISO 20022 has been arriving in US payments in waves for a couple of
years — CHIPS in 2024, Fedwire in 2025. Most of that wave has already
landed. What's still ahead, and dated, is narrower: by November 2026,
several networks — Fedwire, CHIPS, SWIFT cross-border, and others —
stop accepting unstructured free-text addresses for certain parties on
a payment message. A structured Town and Country becomes mandatory,
not optional. If your system has been quietly getting away with
free-text-only addresses because the old message format never
enforced otherwise, that stops working on a fixed date.

That's the kind of failure tollgate is built to catch before it
reaches a clearing network: not "is this XML well-formed," but "will
this specific, dated rule reject this message even though the schema
says it's fine."

## What it actually checks (v1)

One message type only: pacs.008.001.08, the FI-to-FI customer credit
transfer message used across Fedwire, CHIPS, and SWIFT CBPR+.

1. **Schema structure.** Standard XSD validation. This part isn't
   novel — it's the floor everything else stands on.
2. **SWIFT's character set restriction.** ISO 20022 XML allows full
   Unicode. SWIFT's network layer doesn't. A message can be 100%
   schema-valid and still get rejected for using a character outside
   SWIFT's allowed set. Tollgate flags this before you find out the
   hard way.
3. **Address structure, hybrid end-state rules.** The specific
   structured-vs-free-text address requirements that change by
   November 2026, broken out by which party role they apply to
   (because the rules genuinely differ by role — Ultimate Debtor
   follows a stricter rule than plain Debtor, and that distinction is
   easy to miss).
4. **Truncation signals from legacy conversion.** If a field value
   lands at exactly 35 or 70 characters — the old MT line-length
   limits — that's a real signal something got cut off during
   conversion, even though it's still well within the new field's
   allowed length. The schema can't see this. A length check alone
   can't see this either. You need to know what the old boundary was.
5. **Mandatory fields with no legacy equivalent.** A few pacs.008
   fields are required now but had nothing analogous in the old FAIM
   format — meaning a straight auto-conversion has no source data to
   put there at all. That's a different problem than "field is
   missing," and it deserves a different explanation.

Every one of these is sourced. See `docs/SOURCES.md` — if a rule is
in this tool, there's a citation behind it. If I can't trace a rule to
a real document, it doesn't go in.

## What it explicitly does not do

- It is not a SWIFT-certified compliance tool. It will not replace
  MyStandards testing, and I'm not pretending it will.
- It covers exactly one message type in v1: pacs.008.001.08. Not
  pacs.009, not camt.05x, not the rest of the standard. One thing,
  done honestly, before expanding.
- It checks structure and format. It does not validate business logic
  like BIC routing reachability or account existence.
- The character-set restriction is documented for the FIN/MX
  coexistence era. Some networks have discussed loosening this for
  specific cases (accented characters in domestic contexts, for
  example). Confirm current behavior for your specific network before
  treating this as a universal, permanent rule.

## How the AI layer works, and why it's built this way

When tollgate finds a problem, there are two separate jobs: deciding
*that* something is wrong, and explaining *why* it matters and what to
do about it. Those are different jobs and they're handled by different
parts of the system on purpose.

The deciding part is deterministic code — XSD validation, regex
checks, length comparisons against known boundaries. No AI involved.
If tollgate tells you a field violates a rule, that's a fact a
computer checked, not a guess a model made.

The explaining part is where Claude comes in, and only there. Given
an already-identified violation, it writes the plain-English
explanation — what's wrong, why it matters, what probably caused it
if there's a real signal for that. It does not get to decide whether
something is a violation in the first place. It's a translator, not a
judge.

This split exists because I'd rather a user trust every word of an
explanation and occasionally find the tool conservative, than have a
slick explanation sitting on top of a guess. In a space adjacent to
real money movement, that tradeoff isn't close.

## Status

Early. The module structure and the rule list are real and sourced.
The actual rule logic isn't written yet — every validation module
currently raises `NotImplementedError` with a docstring laying out
exactly what it's going to do and why. I'd rather ship an honest
skeleton than a tool that quietly does less than it claims.

## License

Apache 2.0.
