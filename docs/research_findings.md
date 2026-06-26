# Sentinel Risk — Research Findings

## Digital financial reporting and interoperability

The IFRS Foundation explains that digital financial reports use computer-readable structured formats such as XBRL, enabling users to search, extract, and compare disclosures efficiently. The IFRS digital taxonomies provide tags that structure IFRS reporting data for computer-readable use. Product integration requires an appropriate licence for commercial use.

XBRL International describes XBRL as a global, computer-readable standard for reporting. It supports structured comparison across countries and languages, multilingual labels, data validation, and automation. This makes XBRL/iXBRL a logical Phase 2 ingestion path after a robust CSV/XLSX normalization layer.

The FASB overview confirms that XBRL is an XML standard used to tag business and financial reports and that the US GAAP taxonomy supports computer-readable financial-statement data. This supports a modular taxonomy-adapter approach rather than a single universal column schema.

## Regional formats

Sentinel Risk has an English-only interface, but its users read filings from India, China, Japan and South Korea. W3C distinguishes internationalization (designing a product so it can be adapted) from localization (adapting it to a specific region). The relevant part for this product is regional data handling: number, date/time, currency, sorting, symbols, and possible legal requirements.

W3C recommends UTF-8 throughout the application, language declarations, avoidance of string concatenation, and locale-aware handling of numbers, dates, and forms. For Sentinel Risk this means explicit currency codes (INR, CNY, JPY, KRW, USD), explicit reporting units (crore, lakh, million, billion), and explicit fiscal-year conventions on every imported figure.

## Desktop security and distribution

Electron’s official security guidance recommends current framework dependencies, secure content loading, context isolation, process sandboxing, restrictive CSPs, restricted navigation and new-window behavior, sender validation for IPC, and avoiding broad exposure of Electron APIs. The current Sentinel Risk desktop configuration already uses `contextIsolation: true` and disables Node integration but needs the rest of the release hardening baseline.

Electron states that Windows and macOS operating systems warn against unsigned software. Public production release therefore requires platform code-signing; macOS also requires notarization. This should be a release-gate workstream rather than a post-launch task.

## Sources

1. IFRS Foundation, "Digital financial reporting" — https://www.ifrs.org/digital-financial-reporting/
2. XBRL International, "What is XBRL?" — https://www.xbrl.org/the-standard/what/what-is-xbrl/
3. Financial Accounting Standards Board, "About XBRL" — https://www.fasb.org/projects/fasb-taxonomies/about-fasb-taxonomies/about-xbrl
4. W3C, "Localization vs. Internationalization" — https://www.w3.org/International/questions/qa-i18n
5. W3C, "Internationalization Quick Tips for the Web" — https://www.w3.org/International/quicktips/
6. W3C, "Internationalization Best Practices for Spec Developers" — https://www.w3.org/TR/international-specs/
7. Electron, "Security" — https://www.electronjs.org/docs/latest/tutorial/security
8. Electron, "Code Signing" — https://www.electronjs.org/docs/latest/tutorial/code-signing
