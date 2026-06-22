# Sources

Every validation rule in this project traces back to one of the entries
below. If you're adding a new rule, add its source here first — don't
add a rule you can't trace to a primary or clearly-identified secondary
source. This file is what separates Tollgate from a plausible-sounding
AI guess; treat it as load-bearing.

Dates and deadlines in payment-system migrations move. Several of the
dates below have already been extended once (the Fedwire address
requirement was pushed back three times). Re-verify against the
primary source before quoting a date publicly, and note the
verification date next to any claim you re-check.

---

## fedwire-qrg

**Fedwire Funds Service ISO 20022 Quick Reference Guide**
Federal Reserve Banks. Last revised per document: July 25, 2024 (the
guide is itself periodically updated — check for a newer revision
before relying on a specific page reference).

Used for: postal address structure rules (interim vs. hybrid end-state),
US Treasury tax payment formatting requirements for pacs.008, FAIM
3.0.7-to-ISO-20022 data element comparison table, IMAD/OMAD usage.

Retrieved via: https://www.oregonpacificbank.com/wp-content/uploads/2025/04/ISO-20022-Quick-Reference-Guide.pdf
(a bank's hosted copy of the Federal Reserve's guide — if possible,
confirm against the Fed's own FRBservices.org hosting before treating
this as canonical, since it's a secondary hosting of a primary
document).

## address-deadline-2026

**J.P. Morgan: ISO 20022 Migration: Guidance, Messaging & More**
States the November 2026 deadline for fully structured or hybrid
address-format requirements, applying to cross-border payments over
the SWIFT network and clearing systems that mandate hybrid/structured
addresses, explicitly naming Fedwire, CHIPS, SEPA, Swiss Interbank
Clearing (SIC), CHAPS-UK, TARGET2-Euro, and South Africa's SAMOS.

URL: https://www.jpmorgan.com/insights/payments/fx-cross-border/iso-20022-migration

Cross-referenced against: Citibank ISO 20022 Migration FAQs PDF, which
independently states the same November 2026 date for address structure
enforcement and references the SWIFT "brief introduction to the Postal
Address field" knowledge base article.
URL: https://www.citibank.com/tts/sa/iso-20022-migration/assets/docs/ISO-20022-FAQs.pdf

## charset-x

**ECB / T2S character set X definition**
European Central Bank, T2S Change Request T2S-0645-SYS.
Defines character set X as: `a-z A-Z 0-9 / - ? : ( ) . , ' + { } CR LF`
(the document itself notes a historical discrepancy between sources
over whether `{` and `}` are included — the request was to disallow
them, so treat the narrower set without curly braces as the safer
default: `a-z A-Z 0-9 / - ? : ( ) . , ' +` plus CR/LF).

**CORRECTION found during implementation (2026-06-20):** the
definition above, copied directly from research notes, omits the
plain space character. SWIFT's own character set X definition
(see Paiementor and SWIFT Standards MT sources below) lists Space
explicitly as a separate allowed character alongside the letters,
digits, and punctuation. Without it, the regex implementation falsely
flagged completely ordinary text like "Tomas Becker" as a violation —
caught only because charset_rule.py was tested against real generator
output before being trusted. The corrected, implemented pattern is:
`a-z A-Z 0-9 / - ? : ( ) . , ' + SPACE` plus CR/LF. See
tests/test_charset_rule.py::test_no_false_positive_on_plain_text,
which exists specifically to guard against this regressing.

URL: https://www.ecb.europa.eu/paym/target/t2s/governance/pdf/crg/ecb.targetseccrg161122_T2S-0645-SYS.en.pdf

**Paiementor — SWIFT formatting rules and character sets of MT messages**
Lists the SWIFT 'x' character set explicitly including Space as a
distinct allowed character, separate from the letter/digit/punctuation
list: "a b c ... 0123456789 / – ? : ( ) . , ' + CrLf Space".
URL: https://www.paiementor.com/swift-formatting-rules-and-character-sets-of-mt-messages/

**SWIFT Standards MT, November 2021 — General Information**
SWIFT's own standards documentation, independently confirming the same
letter/digit set for the 'x' character set used in field format
indicators.
URL: https://www2.swift.com/knowledgecentre/rest/v1/publications/usgi_20210723/2.0/usgi_20210723.pdf

**XMLdation knowledge base — ISO 20022 character set**
Independently confirms: ISO 20022 XML messages officially use UTF-8
Unicode, but SWIFT adds a rule restricting allowed characters to Basic
Latin on top of the schema-level permission.

URL: https://knowledge.xmldation.com/charset

CAVEAT: a UK Interoperability Working Group record (Bank of England,
Jan 2018) shows extended character set proposals have been discussed
for some market infrastructures, specifically to support accented
characters in domestic use cases. Don't treat character-set-X
restriction as permanently universal across all networks — confirm
current status for your specific target network.
URL: https://www.bankofengland.co.uk/-/media/boe/files/payments/rtgs-renewal-programme/interoperability-working-group/record-of-third-interoperability-working-group-jan-18.pdf

## truncation-pilot

**BNY Mellon: ISO 20022 Webcast Series, Module 8 — SWIFT Platform Update**
Documents that SWIFT's CBPR+ pilot testing (June 2021, 11 pilot banks
including BNP Paribas, Citibank, Deutsche Bank, JPMorgan Chase,
Société Générale) used 11 defined test scenarios: 5 "happy path" and
6 "truncation and warning" scenarios. Confirms truncation-on-conversion
is a named, recognized SWIFT-documented test category, not an inferred
or hypothetical problem.

URL: https://www.bnymellon.com/content/dam/bnymellon/documents/pdf/iso-20022/Module%208_June%202021_Transaction%20Manager%20Update.pdf

**BNY Mellon: "A Deep Dive on pacs.009" (Feb 2021)**
Names specific fields requiring care "to avoid truncation when
translating between MX and MT messages" — End-to-End Identification,
Transaction Identification, UETR, Clearing System Reference.

URL: https://www.bny.com/assets/corporate/documents/pdf/iso-20022/learning-guide-module-5.pdf

## fedwire-faim-comparison

**STATUS: UNVERIFIED, NOT USED IN ANY SHIPPED RULE (2026-06-20).**
This citation was carried over from early research notes and cited in
mandatory_gap_rule.py's original (pre-implementation) docstring, but
the underlying Fedwire QRG page (pages ~23-25, "Comparison – FAIM
3.0.7 Tags to ISO 20022 Data Elements") was never actually fetched or
checked directly -- only referenced secondhand. When mandatory_gap_rule.py
was actually implemented, this framing was replaced with the verified
uetr-fedwire-mandatory finding below instead of building a rule on an
unconfirmed citation. Leaving this entry in place rather than deleting
it, so the unverified claim is visible and can be checked properly in
a future session if someone wants to add a second mandatory-gap rule.

**Original unverified claim, for the record:** Fedwire ISO 20022 Quick
Reference Guide documents several FAIM tags — the {6100}, {6200},
{6210}, {6300}, {6310}, {6500} series — as having "No equivalent" in
the ISO 20022 / MX format.

## uetr-fedwire-mandatory

**Federal Reserve Financial Services — Format Frequently Asked
Questions.** States plainly that UETR is a mandatory data element for
value messages (pacs.008, pacs.009, pacs.004), provides a universally
unique end-to-end transaction reference, and that the Fedwire Funds
Service checks UETR for proper format (though not for uniqueness).

URL: https://www.frbservices.org/resources/financial-services/wires/faq/iso-20022/format

**Verified against the actual vendored XSD (2026-06-20):** UETR has
minOccurs="0" in PaymentIdentification7 -- genuinely optional at the
schema level. This is the clean, directly-sourced version of the
"network requires more than the schema does" gotcha this project is
built around: a message can omit UETR entirely, validate against the
XSD with zero errors, and still get rejected by Fedwire specifically.
Unlike the FAIM-comparison claim above, both halves of this claim
(schema optionality, network mandate) are independently confirmed
against primary sources.

CAVEAT: this is documented as a Fedwire-specific requirement in the
source above. Don't assume every ISO 20022 network enforces UETR the
same way, even though SWIFT's broader gpi/UETR mandate for
cross-border payments suggests it's increasingly universal in
practice -- confirm for your specific target network.

## xsd-source

**ISO 20022 Message Definitions catalogue** (current versions):
https://www.iso20022.org/iso-20022-message-definitions
As of this research, the catalogue's current published version is
pacs.008.001.14 (direct XSD link:
https://www.iso20022.org/message/23500/download). Fedwire, CBPR+, and
major bank guidance (Citi, JPMorgan, BNY) reference pacs.008.001.08
instead — confirm which version your target network has actually
pinned to before assuming "newest" is correct.

**ISO 20022 Messages Archive** (superseded versions):
https://www.iso20022.org/catalogue-messages/iso-20022-messages-archive
pacs.008.001.08 (FIToFICustomerCreditTransferV08) lives here, not in
the current catalogue — it was superseded and archived. Found under
the "Payments Clearing and Settlement V09" message set, archived
01 February 2019.
  - Direct XSD download (confirmed working, verified by fetch on
    2026-06-20): https://www.iso20022.org/message/14231/download
  - This is a zip; unzip and verify the exact filename(s) inside —
    ISO 20022 message sets sometimes bundle shared dependency XSDs
    alongside the message-specific one.

Pull the XSD directly from one of the two URLs above, not from a
third-party GitHub mirror, even though such mirrors exist (e.g.
sladjan/xsd-camt, yudhik/example-iso-20022) — they're convenience
copies with no guarantee of staying unmodified or available. Note in
the vendored file (a header comment is fine) which URL it came from
and the date it was pulled, since archived-message-set contents could
theoretically be revised.

## migration-timeline-general

Background only, not used for any specific validation rule, but
relevant for README framing:

- CHIPS migrated to ISO 20022: April 2024 (Clearing House)
- Fedwire Funds Service ISO 20022 implementation: March 10, 2025
  (per Fedwire QRG footnote 16), with related communications also
  referencing July 14, 2025 as a relevant date for full mandatory
  cutover in some sources (PCBB FAQ) — there were phased dates;
  don't assert a single date without checking which milestone you mean.
- SWIFT MT/MX coexistence period for cross-border (CBPR+) ended:
  November 2025.
- Source for the above: PCBB ISO 20022 FAQ
  (https://www.pcbb.com/products/cash-management/domestic-payments/iso20022-faq),
  cross-referenced against BNY Mellon's ISO 20022 Migration Strategy
  document.

**Do not claim in README that 2026 is "when Fedwire/CHIPS/CBPR+ all
migrate" — they already did. 2026's relevant deadline is the address-
structure enforcement above (address-deadline-2026), which is a
narrower and more accurate hook.**

## known-limitations

Found during a deliberate review/polish pass (2026-06-20), testing
deliberately messy real-world-shaped input rather than only the clean
fixtures the test suite generates:

- **Multi-transaction messages, field path ambiguity.** The schema
  allows CdtTrfTxInf to repeat (maxOccurs="unbounded") -- a single
  pacs.008 message can carry multiple transactions. All four
  non-XSD rules (charset, address, truncation, mandatory-gap) correctly
  find violations regardless of which transaction they're in, but the
  reported field_path (e.g. "FIToFICstmrCdtTrf/CdtTrfTxInf/Dbtr/Nm")
  does not include a transaction index, so two violations in different
  transactions can report identical-looking paths. Not a crash, not
  silently missed -- just ambiguous about which transaction, which
  matters less for v1's single-message-at-a-time CLI usage but would
  matter if this is ever extended to batch/multi-transaction reporting.
- **Several real bugs were found and fixed in this same pass** by
  deliberately testing non-XML input, empty files, binary files, and
  directories-passed-as-files -- see the inline comments in
  validation/xsd_validator.py and cli.py for what broke and how it was
  fixed. Listed here too so the pattern (clean fixtures passing tests
  doesn't mean messy real input is handled) is visible at a glance.

## data-handling-ai-boundary

Found and fixed during a review pass (2026-06-20): an earlier version
of explain/explainer.py sent Violation.raw_value to the Anthropic API
verbatim as part of building an explanation. For charset_violation and
truncation_suspected specifically, raw_value can contain the full
content of a sensitive field -- a real person's or company's name, an
address fragment, taken directly from a real payment message the user
is checking with Tollgate. Sending that to a third-party API without
explicit, informed user consent is not acceptable for a tool whose
entire premise is processing real bank payment data.

**The fix:** raw_value is never included in the prompt sent to the
API. Checked first whether it was actually needed for explanation
quality -- it wasn't. Every rule's `message` field was already written
to contain only the safe-to-send, isolated detail the explainer
needs (the specific offending character, the exact length and
boundary, the line count, the absent field name) without the full
sensitive value attached. See explain/prompts.py and
explain/explainer.py for the in-code documentation of this boundary,
and tests/test_data_handling.py for tests that mock the API client and
directly verify a real sensitive value never appears in the actual
payload sent.

**What this restriction does NOT cover:** raw_value is still included
in local outputs -- the CLI's markdown report (--output) and JSON
output (--json) both show it when present, since a user's own local
report displaying their own data back to them is not the same risk as
an API call sending that data to a third party. Only the network
boundary to Anthropic's API is restricted.

**Scope of this finding:** only charset_rule.py and truncation_rule.py
ever set raw_value at all; address_rule.py, mandatory_gap_rule.py, and
xsd_validator.py never populate it, so they were never exposed to this
issue in the first place.

**What --explain itself does send:** rule_id, field_path, severity,
the deterministic message (already vetted as safe per above), and
source_ref. None of these should constitute PII on their own --
field_path is a structural XML path (e.g. "Dbtr/Nm"), not a value.

## sixth-rule-candidate-currency-decimal-precision (RESEARCH ONLY -- NOT IMPLEMENTED)

Researched 2026-06-21, NOT yet built into a validation rule. Recorded
here so the research is preserved and sourced before any code gets
written, per this project's own convention -- research and citation
first, implementation second.

**THE GOTCHA:** ISO 4217 defines a "minor unit" exponent per currency
-- how many decimal places that currency actually supports. Most
currencies use 2 (USD, EUR, GBP). Some use 0 -- no decimals at all
(JPY, KRW, VND, and others). A few use 3 (KWD, BHD, OMR, JOD, TND,
LYD, IQD). Source: ISO.org's own page on ISO 4217
(https://www.iso.org/iso-4217-currency-codes.html), cross-referenced
against three independent payment-processing technical references
(Adyen, Datatrans, LegalClarity) which all state the same exponent
groupings consistently.

**VERIFIED AGAINST THE ACTUAL VENDORED XSD (2026-06-21):**
ActiveCurrencyAndAmount_SimpleType (used for IntrBkSttlmAmt) defines
fractionDigits="5", totalDigits="18" -- the schema permits up to 5
decimal places for ANY currency, regardless of what that specific
currency's own ISO 4217 minor-unit rule actually allows. This is the
same shape as every other rule in this project: the schema is
deliberately more permissive than real-world correctness rules layered
on top of it. A JPY amount like "1000.50" (JPY supports 0 decimal
places) would pass XSD validation cleanly and still be objectively
wrong -- not a network-rejection case like charset_violation or
address_too_many_lines, but a different failure mode: a value that's
schema-valid and simply incorrect, which a receiving system might
silently misinterpret (treating 1000.50 JPY as a fractional-yen amount
that doesn't exist) rather than reject outright. Worth flagging this
distinction if this rule is ever built -- the explanation for this one
should be careful not to overstate it as a guaranteed rejection the
way the address/charset rules can, since the actual failure mode here
(silent misinterpretation vs hard rejection) is less certain and
depends on the receiving system's own handling.

**What would be needed to actually build this:** a currency ->
exponent lookup table (the three tiers above), checked against the
`Ccy` attribute already present on amount elements like
IntrBkSttlmAmt. The decimal-place count of the element's text content
would need to be checked against the matching currency's expected
exponent. NOT YET BUILT. Note for whoever picks this up: the lookup
table itself needs to be sourced directly from ISO 4217's official
published table (via SIX Group, who maintain it on ISO's behalf), not
copied from a secondary blog post's partial list -- the sources found
during this research were consistent with each other but none of them
is the primary published standard itself.

## seventh-rule-candidate-bicfi-clrsysmmbid-precedence (RESEARCH ONLY -- NOT IMPLEMENTED)

Researched 2026-06-21, NOT yet built. A genuinely DIFFERENT kind of
gotcha than the project's existing six rules -- worth naming the
distinction explicitly before deciding whether to build it.

**THE GOTCHA:** An agent element (DbtrAgt, CdtrAgt, etc.) can carry
both a BICFI and a ClrSysMmbId (clearing system member ID / routing
number) simultaneously -- the schema's FinancialInstitutionIdentification18
type allows both as independent optional siblings in a plain sequence,
not an xs:choice. Deutsche Bank's own CBPR+-based payments formatting
guide states explicitly: "In case of conflicting information, the
BICFI will take precedence over additionally provided ClrSysMmbId
and/or Name/Postal [Address]" (https://corporates.db.com/files/documents/Payments-Formatting-Guide-for-high-value-payments-ISO-20022.pdf).

**VERIFIED AGAINST THE ACTUAL VENDORED XSD (2026-06-21):**
FinancialInstitutionIdentification18 lists BICFI (minOccurs=0) and
ClrSysMmbId (minOccurs=0) as independent sibling elements in a plain
xs:sequence -- both can be populated with no schema-level constraint
forcing them to agree.

**WHY THIS IS A DIFFERENT FAILURE MODE than the project's existing six
rules:** every other rule in this project catches something that gets
REJECTED (a hard failure) or is internally inconsistent in an
objectively checkable way (wrong decimal count, wrong character).
This gotcha is about SILENT PRECEDENCE -- the message doesn't get
rejected at all; one field quietly wins over another, and if the
sender intended the routing number to matter (e.g. for a domestic
clearing system) but the BICFI doesn't match, the payment may route
differently than intended without any error being raised anywhere.

**HONEST LIMITATION, the reason this is research-only and not
implemented:** Tollgate cannot actually verify whether a given BICFI
and ClrSysMmbId value are "in conflict" with each other -- that would
require an external BIC-to-routing-number directory/lookup table,
which does not exist anywhere in this project and would be a
significantly larger undertaking than any of the six existing rules
(a real BIC registry is large, requires its own licensing/sourcing
research, and changes over time). What this rule COULD honestly do
without that lookup table: flag whenever BOTH BICFI and ClrSysMmbId
are populated on the same agent at all, with an explanation noting the
precedence rule and that this is worth double-checking even though
Tollgate cannot confirm an actual conflict exists. That's a much
weaker claim than the project's other rules make, and worth being
explicit about in the explanation text if this is ever built --
overstating certainty here would be the kind of overclaiming this
project's brief explicitly warned against.

**Additional scope needed if built:** the generator
(synthetic_fixtures.py) does not currently populate ClrSysMmbId at all
-- `_build_agent()` only ever sets BICFI. Building this rule would
also require extending the generator, similar to how
include_ultimate_parties was added for the address rules.

## eighth-rule-candidate-bicfi-name-address-mutual-exclusion (RESEARCH ONLY -- NOT IMPLEMENTED)

Researched 2026-06-21, NOT yet built into a validation rule. Recorded
here so the research is preserved and sourced before any code gets
written, per this project's own convention.

**THE GOTCHA:** CBPR+'s usage guideline for agent identification
states a textual rule not present anywhere in the XSD: if BICFI is
present on an agent, Name and Postal Address must NOT also be
present. The exact wording, reproduced verbatim across multiple
official CBPR+ usage guideline documents (see sources below): "If
BICFI is present, then (Name & Postal Address) is NOT allowed
(ClearingSystemMemberIdentification and LEI may complement) -- However,
in case of conflicting information, the BICFI will always take
precedence." The same document states the reverse direction too: "If
BICFI is absent, (Name & Postal Address) OR [(Name & Postal Address)
and ClearingSystemMemberIdentification] must be present." So this is a
genuine mutual-exclusion rule, not a one-directional recommendation.

A parallel rule exists for Debtor/Creditor party identification
(distinct element, AnyBIC instead of BICFI, but identical shape): "If
AnyBIC is present, then (Name and Postal Address) is NOT allowed."

**VERIFIED AGAINST THE ACTUAL VENDORED XSD (2026-06-21):**
FinancialInstitutionIdentification18 (used for every Agt element --
DbtrAgt, CdtrAgt, InstgAgt, InstdAgt, IntrmyAgt1/2/3, etc.) lists
BICFI, ClrSysMmbId, LEI, Nm, PstlAdr, and Othr as six independent
sibling elements in a plain xs:sequence, every one minOccurs="0" with
no xs:choice, no co-occurrence constraint, nothing. A message can
validly populate BICFI AND Nm AND PstlAdr simultaneously on the same
agent and pass XSD validation with zero errors -- the schema places
no structural relationship between them at all. Confirmed the same
shape on the party side: PartyIdentification135 (used for Dbtr, Cdtr)
has Nm and PstlAdr as direct siblings, with AnyBIC nested independently
inside Id (Party38Choice) -- again, no schema-level exclusivity.

This is structurally distinct from the seventh-rule-candidate above
(BICFI/ClrSysMmbId precedence): that one is about whether two
*conflicting values* on the same agent disagree about routing: this
one is about *simultaneous presence* of fields that should never
co-occur in the first place, regardless of whether their values agree
or conflict. Different failure mode, different (much simpler) check --
this one is pure structural co-occurrence, no value-conflict judgment
needed, no external lookup table required. That makes it considerably
more buildable than the seventh candidate.

**Sources -- the exact same textual rule, verbatim, found across
eight separate official SWIFT CBPR+ / Lynx usage guideline documents,**
which is a stronger corroboration chain than most rules in this file
get from independent secondary sources, since this is the same
standards body's own canonical wording repeated across its message
family rather than several authors independently describing the same
behavior:

- **CBPRPlus-pacs.008.001.08_FIToFICustomerCreditTransfer Usage
  Guideline** (the exact message type this project validates) --
  states both the agent rule (BICFI) and the party rule (AnyBIC)
  explicitly, plus the reverse-direction requirement.
  URL: https://www.clearstream.com/caas/v1/media/4151636/data/56d74336ef4c09ed02789f28d1ab6f3f/pacs-008-2.pdf
- **CBPRPlus-pacs.002.001.10_FIToFIPaymentStatusReport Usage Guideline**
  -- identical agent rule, plus an additional detail not seen in the
  pacs.008 guideline: "If AnyBIC is absent, then Name is mandatory."
  and "If Postal Address is present then Name is mandatory."
  URL: https://www.clearstream.com/caas/v1/media/4151632/data/b19516ff2c3e11879b5be608f8053513/pacs-002.pdf
- **CBPRPlus-camt.052/053/054 and camt.105 Usage Guidelines** --
  same verbatim agent rule repeated across the reporting message
  family, confirming this is a message-family-wide CBPR+ principle,
  not something specific to pacs.008.
  URLs: https://www.clearstream.com/caas/v1/media/4151626/...
  (camt.052), .../4151644/... (camt.053), .../4151648/... (camt.054),
  .../4847152/... (camt.105)
- **Lynx (Payments Canada) ISO 20022 message specification** --
  independently confirms the same rule, explicitly noting "This rule
  is inherited verbatim from CBPR+," for both pacs.009 and its broader
  companion document -- useful as cross-confirmation that this isn't
  a Clearstream-specific reinterpretation, since Lynx is a different
  market infrastructure entirely just adopting the same CBPR+ baseline.
  URLs: https://www.payments.ca/sites/default/files/lynx_financial_institution_credit_transfer_pacs.009_core.pdf
  and https://www.payments.ca/sites/default/files/2022-08/lynx_iso_20022_message_specification_companion_document_for_core_messages.pdf
- **Deutsche Bank Corporate Bank Payments Formatting Guide, May 2025**
  -- a bank's own client-facing implementation guide independently
  stating the same rule in its own words ("As per CBPR+ if BICFI is
  present, then Name & Postal Address is not allowed"), useful as a
  practitioner-level confirmation that this is actually enforced in
  real processing, not just a guideline nobody follows.
  URL: https://corporates.db.com/files/documents/Payments-Formatting-Guide-for-high-value-payments-ISO-20022.pdf

**CAVEAT, same shape as every other rule in this file:** this is a
CBPR+/SWIFT-network rule, not a universal ISO 20022 rule. Don't assume
every clearing system enforces this the same way -- confirm for the
specific target network before generalizing the explanation text.
Severity should likely be `error` rather than `warning`, since unlike
the currency-decimal rule (a "might be silently misinterpreted" case)
this is stated as a hard textual rule with explicit rejection
implications ("NOT allowed"), closer in certainty to the charset and
address-structure rules.

**What would be needed to actually build this:** walk every Agt
element (DbtrAgt, CdtrAgt, InstgAgt, InstdAgt, IntrmyAgt1/2/3,
PrvsInstgAgt1/2/3) and every party element (Dbtr, Cdtr) checking: does
BICFI/AnyBIC co-occur with Nm or PstlAdr on the same element? No
external lookup table needed (unlike the seventh candidate) -- this is
pure structural presence-checking, similar in implementation
complexity to the existing address-structure rule.

**IMPORTANT, VERIFIED FINDING (2026-06-21):** `_build_agent()` in
synthetic_fixtures.py currently sets BOTH BICFI and Nm on every agent
it builds, unconditionally, by design -- its own docstring calls this
"the simpler, more common path." Every DbtrAgt and CdtrAgt in every
single baseline fixture this project has ever generated already
violates this CBPR+ rule as researched above. This has never been
caught because no rule currently checks for it.

This means building this rule is NOT a simple additive change --
build_valid_baseline() would need `_build_agent()` fixed first (BICFI
without Nm, as the actual common/correct case) before this rule could
be added without every single existing "clean" baseline fixture
immediately and incorrectly failing it. This is the same category of
bug as the JPY-decimal generator bug found while building the sixth
rule (see currency_decimal_mismatch above) -- a latent baseline-
generator defect that only became visible once a rule existed to
check for it. Whoever picks this up should fix _build_agent() and
verify test_inject_error.py's existing tests for the other 6 rules
still pass against the corrected baseline (they should -- this change
doesn't touch address/charset/truncation/mandatory-gap/currency
fixtures' shape) before adding the new rule and injector on top.

The generator would then need a new injector that deliberately sets
BICFI alongside Nm/PstlAdr (the now-fixed-to-be-wrong combination) to
produce the labeled violation fixture for eval-harness ground truth.


