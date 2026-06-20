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

**Fedwire ISO 20022 Quick Reference Guide**, "Fedwire Funds Service
Comparison – FAIM 3.0.7 Tags to ISO 20022 Data Elements" section
(same document as fedwire-qrg above, pages ~23-25 in the July 2024
revision). Documents several FAIM tags — the {6100}, {6200}, {6210},
{6300}, {6310}, {6500} series — as having "No equivalent" in the
ISO 20022 / MX format, meaning legacy systems carrying this data have
no source field to map from when generating these MX elements.

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
