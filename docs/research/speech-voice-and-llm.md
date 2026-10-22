# Speech, voice cloning and language-model options for Hikaya (ElevenLabs and Azure)

Researched 2026-10-17. Every page cited below was opened on that date ("seen 2026-10-17"). Source ids like [E2] resolve to a URL in the Sources index at the bottom. Pages were read through a summarising fetch tool, so re-check any number in the provider's console or pricing page before you add money. Anything I could not confirm from a primary source is marked UNVERIFIED and repeated in the list at the end. Non-primary sources (an aggregator) are labelled "non-primary" wherever a number or fact comes from them.

Two method notes. (1) Azure's public pricing pages render every price as "$-" to a plain fetch, so Azure prices below come from Microsoft's own Azure Retail Prices API (prices.azure.com), which is a primary Microsoft source but shows list prices for one region (eastus, eastus2 or Global) and is not a quote. (2) The ElevenLabs API-pricing page lists "included per plan" quantities without column labels; I matched them to plans by position and checked the arithmetic (see section 7).

## Summary and recommendation

1. Use Azure for the language-model steps (polish, translate, label) and for speech-to-text, paid from the Azure credits; use ElevenLabs Starter for narration and for all 3 voice clones; keep Azure ar-JO neural TTS (SanaNeural female, TaimNeural male) as the coded fallback behind one interface.
2. Jordanian accent: no ElevenLabs page names Jordanian; accent comes from the voice, so the documented routes are a clone of a Jordanian speaker, a Voice Design prompt, or a Voice Library voice (a "Jordanian" tag was only seen at a non-primary aggregator). Azure has a real ar-JO locale with two standard neural voices and no HD voice.
3. Key prices (USD, seen 2026-10-17): ElevenLabs Starter $6/month ($1 first month, promo shown "until Oct 18"), TTS API $0.08 per 1K characters (v4, v3, Multilingual v2) or $0.04 (Flash, Turbo), Scribe v2 $0.22 per hour; Azure fast transcription $0.36/h, real-time $1.00/h, neural TTS $15 per 1M characters, F0 free 5 h STT and 0.5M TTS characters per month, GPT-5.4-mini $0.75 in / $4.50 out per 1M tokens, GPT-4.1-mini $0.40 / $1.60.
4. Budget: the whole test costs about $8 (base) to $17 (3x safety margin) with ElevenLabs primary, of which ElevenLabs cash is $6 to $11 and the rest is Azure credits; Azure-only is about $5 to $10.5 but its voice-cloning route is access-gated and Arabic output is unconfirmed. $25 is enough; the cheapest sensible plan is one Starter month plus Azure on credits.
5. Spend rules: an in-app ledger that reserves the estimated cost before every paid call and hard-stops at the cap, content-addressed caching of STT, LLM and TTS results, ElevenLabs auto top-up off with a per-key credit quota, and no reliance on Azure budgets (they only notify, with 8 to 24 h data lag).
6. Biggest unknowns: the Prohibited Use Policy body text could not be retrieved, Free-plan API access is never stated plainly, no provider publishes Jordanian-dialect STT accuracy, and Arabic quality of every candidate LLM and TTS model needs a short listening and reading test (about $1).

---

## 1. ElevenLabs instant voice cloning (IVC) through the API

| Item | Finding | Source |
|---|---|---|
| Minimum plan | **Starter.** The billing page says cloning is only available on Starter and above. The pricing page lists "Instant Voice Cloning" on the Starter card (not on Free). Professional Voice Cloning needs Creator or higher. | [E4] [E1] [E7] |
| Monthly price | Starter **$6/month** list. The pricing page shows "$1 per month" with "$6 First month 83% off" and "Until Oct 18"; the API-pricing page labels Starter "$6 (first month $1)". 83% off $6 is $1.02, so I read $6 as the regular price. Whether the promo applies to this owner and whether "Until Oct 18" is inclusive: UNVERIFIED. Creator is $22 ($11 first month). | [E1] [E2] |
| Credits on Starter | 30k credits per month; commercial licence included; custom voice slots: the account docs use a Starter example of 10 slots, enough for 3 clones. | [E1] [E33] |
| Free tier and API | Cloning is **not** available on Free. Whether Free can call the API at all is **never stated plainly** (UNVERIFIED): the docs imply it can (they say Voice Library voices "are not available via the API to free tier users", the Scribe concurrency page lists a Free row, and Pay As You Go "unlocks APIs that are disabled on the free plan, such as Music and Sound Effects"), but no page says "API on Free: yes". Free users are non-commercial only and need a personal email; free-tier use can be switched off by the abuse system for VPN or shared IPs, which a cloud-hosted backend may trigger. | [E14] [E27] [E5] [E10] [E33] |
| Endpoint and SDK | `POST https://api.elevenlabs.io/v1/voices/add`, multipart: `name` (required), `files` (required), `remove_background_noise`, `description`, `labels`. Response: `voice_id` and `requires_verification` (boolean). Python: `client.voices.ivc.create(name=..., description=..., files=[...])`. | [E8] [E9] [E29] |
| Sample guidance | At least 1 minute, ideally 1 to 2 minutes of clean audio; more than 2 to 3 minutes adds little; MP3 at 128 kbps or higher (FAQ says 192 kbps or higher; the page does not reconcile these). IVC works in any language supported by Flash v2.5 and Multilingual v2. File-size limit: not stated (UNVERIFIED). | [E6] |
| Consent step | In the web flow you must confirm "that you have the right and consent to clone the voice" before saving. The concept page says both IVC and PVC include a voice-verification step (voice-captcha technology to confirm the person providing the sample is the requester), calls it a safeguard that cannot guarantee ownership, and puts responsibility for authorised use on the creator under the Terms and AI safety policies. How or when `requires_verification` becomes true for an API-created clone, and how to complete it from code, is not documented (UNVERIFIED). | [E6] [E7] [E8] |
| Safeguards | Cloning of celebrity and other high-risk ("no-go") voices is blocked; generated audio is traceable to the account; PVC needs technological verification; misuse can be reported. | [E13] [E12] |
| Recorded vs uploaded | The IVC guide says "upload or record your audio" and then the same consent confirmation; **no difference in treatment is documented** (UNVERIFIED either way). For Hikaya's own records, have the speaker record in-app so provenance is clear, and store a consent record per person regardless. | [E6] |

### What the Terms say (last updated 09 October 2026) [E10]

- Voice models are meant to resemble "your voice or a voice you're authorized to share" (section 4(b)). You must not submit input unless you hold all rights needed to license it, and you represent that your content, voice models and ElevenLabs' use of them will not violate anyone's rights (section 4(g)).
- You keep ownership of input and output but grant ElevenLabs a long-lasting, non-exclusive, worldwide, sublicensable licence to use content to provide and improve the services (4(c), 4(d)). Training use can be opted out in the "Data use" menu, not retroactively (4(i)). Deletion of voice models made from your recordings can be requested in the account. ElevenLabs states it will not commercialise your voice on a standalone basis without permission.
- The Terms set out no separate consent workflow for recording third parties. They bar free users from commercial use and require users to be 18 or of legal age.
- Practical consequence for Hikaya: staff and storytellers who opt in should give written (or recorded) consent that names ElevenLabs as a processor, covers the licence above and says how to withdraw (delete the clone in ElevenLabs and in Hikaya).

### What the Prohibited Use Policy says (last updated 09 October 2026) [E11]

Only partial. The page text I could retrieve shows the section headings, including "Deception, Manipulation and Impersonation", "Privacy and Personal Data" and "Lawful Use and the Rights of Others", but **not their body text**. What is visible: the policy covers input and output including voice samples; anyone who believes their voice was used without consent can file an "Unauthorized Use of Voice" report; attempting to violate the policy is itself a violation; some higher-risk uses may need approval or extra safeguards; enforcement ranges from removal to account termination with an appeal route. The specific consent and impersonation rules are **UNVERIFIED**; read https://elevenlabs.io/use-policy in a browser before launch.

---

## 2. ElevenLabs text-to-speech for Arabic

### Models, Arabic support and API price

| Model id | Arabic | Per-request character limit | API price per 1K characters | Source |
|---|---|---|---|---|
| `eleven_v4` | Yes (`ar`); flagship, "recommended for highest quality" | 10,000 | $0.08 | [E3] [E19] [E2] |
| `eleven_v4_turbo` | Yes (`ar`); about 100 ms median latency | not listed | $0.04 | [E3] [E2] |
| `eleven_v3` | Yes (`ar`); previous generation | 5,000 | $0.08 | [E3] [E2] |
| `eleven_v3_conversational` | Yes (`ar`); about 280 ms | not listed | $0.04 | [E3] [E2] |
| `eleven_multilingual_v2` | Yes, listed as Arabic (Saudi Arabia, UAE); "most stable for long-form" | 10,000 | $0.08 | [E3] [E18] [E2] |
| `eleven_flash_v2_5` | Yes; about 75 ms; lowest price per character for API use | 40,000 | $0.04 ("Flash / Turbo") | [E3] [E18] [E2] |
| `eleven_flash_v2` | **No** (English only) | 30,000 | n/a | [E3] |

- **Credits or characters?** The subscription is measured in credits (Free 10k, Starter 30k, Creator 121k, Pro 600k per month) [E1]. On the website, v3 costs 1 credit per character and API calls are discounted [E39]; Flash v2.5 is described as 50% cheaper per character for API use [E3]. The exact credits-per-character for each model and plan are not published on the pages I read (UNVERIFIED); the API-pricing page expresses prices in dollars per 1K characters, and every API response carries a `character-cost` header you can log (Python: `with_raw_response.convert(...)`) [E2] [E31]. Pay As You Go balances are stored as a dollar value [E4].
- **Docs disagree on v4 language count:** "90+" on the models page and "about 80, including Arabic" on the v4 page; neither mentions Arabic dialects [E3] [E19].
- **Best model for natural Arabic:** no Arabic-specific benchmark is published (UNVERIFIED). The docs recommend `eleven_v4` for highest quality and long-form narration, and `eleven_multilingual_v2` for stability [E20] [E3]. v4 has no SSML and no speed or style sliders [E19]. Decide with a listening test of the same 3 paragraphs on v4, Multilingual v2 and Flash v2.5 (about $0.20 per 1,000 characters across the three: 0.08 + 0.08 + 0.04).

### Voice Library voices through the API on a low plan

- "Voice Library voices are not available via the API to free tier users" [E14]. Starter is a paid plan, so that rule does not apply; the docs do not list any further plan gate for library voices on the API.
- Per-voice limits still apply: owners can restrict who may use a voice, and some voices carry a credit multiplier (a 2x voice costs twice the credits) [E14] [E15]. Free users see "This voice is not available for free users" for paid-only voices [E15]. Saved library voices do not use custom voice slots [E14].
- Search endpoint `GET /v1/shared-voices` accepts `language`, `accent`, `locale`, `gender`, `age`, `category`, `use_cases`, `search`, `sort` and `page_size` (max 100); the per-voice object includes a `free_users_allowed` flag [E22]. In the app, the accent filter appears after a language is chosen [E14]. Allowed values for `accent` are not enumerated (UNVERIFIED).
- Language filtering: voices carry a language tag (for the Professional category, the language they were cloned in) [E37].

### Is there a documented way to get a Jordanian accent?

No page documents a Jordanian preset. The documented levers are:

1. **Accent comes from the voice, not the language setting.** "The language is determined by the text, while the accent and pronunciation are determined by the voice itself"; `language_code` only steers text normalisation and is not supported for multilingual_v2 models [E17] [E16] [E32].
2. **Clone a Jordanian speaker.** v4 keeps the reference voice's original accent when the target language matches the reference language [E19]. IVC may struggle with uncommon accents; Professional Voice Cloning (Creator plan or higher, roughly 30 minutes to 3 hours of audio) is the documented upgrade, and you cannot change a clone's accent after creation, only its samples [E36] [E7]. This is the most reliable route for staff and storytellers who are Jordanian.
3. **Voice Library accent filter.** Exists, but whether a "Jordanian" value exists in the official library is UNVERIFIED. Non-primary: the aggregator Famulor shows two Jordanian-accent ElevenLabs Arabic voices (male, "Abd Ulrahman" and "Bilal - Deep, rich, grounded baritone"), and an Arabic accent list of Saudi (15 voices), Modern Standard (9), Egyptian (8), Jordanian, Moroccan, Algerian, Gulf, Kuwaiti, Omani, American, with no Levantine, Lebanese or Syrian entries [F1] [F2]. No voice ids, no confirmation that they work on Starter.
4. **Voice Design** (prompt-to-voice). The docs say to state language and regional variant first and give the example "Native Arabic, soft Gulf (UAE) accent influence"; Jordanian is not mentioned, so a "Native Arabic, thick Jordanian (Levantine) accent" prompt is a try-it step, not a promise. The only charge is the credits for the preview text, and saving uses a voice slot. Plan availability is not stated [E21].
5. v4 audio tags can nudge accent, "results vary" [E19].

Fallback if none sounds Jordanian: Azure ar-JO voices (section 5), or MSA narration with the best Arabic voice, as the owner already planned.

---

## 3. ElevenLabs speech-to-text (Scribe)

| Item | Finding | Source |
|---|---|---|
| Models | `scribe_v2` (batch, flagship), `scribe_v2_realtime` (WebSocket, about 150 ms), `scribe_v2_medical`; `scribe_v1` deprecated. | [E23] [E3] |
| Price | **Scribe v2 and v2 Medical $0.22 per hour**; Scribe v2 Realtime $0.39 per hour. Add-ons: keyterm prompting +$0.05/h (v2), transcript editing +$0.07/h. The API reference gives surcharges of 20% for keyterms, 30% for transcript editing and 10% for speaker-role detection. | [E2] [E24] |
| Arabic accuracy band | Arabic (`ara`) is in the **"Good" band: word error rate above 10% and at most 20%**. No dialect breakdown. | [E23] |
| Word timestamps | Yes. Each word has `start`, `end`, `text`, `type`, `logprob`, `speaker_id`. `timestamps_granularity` is `none`, `word` (default) or `character`. | [E23] [E24] |
| Dialect handling | **Not documented** in the Scribe docs (UNVERIFIED). The Arabic marketing page (stale: it still names Scribe v1 and gives two inconsistent WER figures, 3.1% and 11.1%) lists the Arabic groups MSA, Egyptian, Levantine (Syrian, Lebanese, Palestinian), Gulf and Maghrebi, with no Jordanian entry and no per-dialect accuracy. | [E26] |
| Request options | `language_code` (ISO 639-1 or 639-3, default auto-detect), `diarize` (up to 32 speakers), `tag_audio_events` (default true), `num_speakers`, `keyterms`, `no_verbatim`, webhook. | [E24] |
| Limits | Docs: files up to 3 GB and 10 hours; the API reference says 5.0 GB (the pages disagree). STT concurrency: Free 8, Starter 12, Creator 20. | [E23] [E24] [E27] |

For a 2-minute story: set `language_code="ara"` (or `"eng"`), `timestamps_granularity="word"`, `diarize=False`, `tag_audio_events=False`.

---

## 4. ElevenLabs Python SDK basics

Package `elevenlabs` on PyPI (latest stable 2.73.0, released 2026-10-15; a 3.0.0a1 pre-release exists; Python 3.8 or newer) [E28]. Install with `pip install elevenlabs`. Sync client `ElevenLabs`, async client `AsyncElevenLabs` [E29].

```python
from io import BytesIO
from elevenlabs.client import ElevenLabs

client = ElevenLabs(api_key=ELEVENLABS_API_KEY)          # 1. client

# 2. text to speech (quickstart passes the result to play(); treat it as audio bytes/chunks)
audio = client.text_to_speech.convert(
    text=polished_text,
    voice_id=VOICE_ID,
    model_id="eleven_v4",                  # or "eleven_multilingual_v2", "eleven_flash_v2_5"
    output_format="mp3_44100_128",
)

# 3. instant voice clone (Starter plan or higher)
voice = client.voices.ivc.create(
    name="Staff - Name",
    description="Consent ref 123",
    files=[BytesIO(open("sample.mp3", "rb").read())],
)
print(voice.voice_id)                       # response also has requires_verification

# 4. Scribe speech to text with word timestamps
tx = client.speech_to_text.convert(
    file=BytesIO(open("story.mp3", "rb").read()),
    model_id="scribe_v2",
    language_code="ara",
    timestamps_granularity="word",
    diarize=False,
    tag_audio_events=False,
)
# tx.text and tx.words (each with start, end, text, type)
```

Sources: [E30] [E9] [E25] [E29] [E24]. Notes: the SDK README and quickstart do not show `speech_to_text.convert` or the exact return type of `convert`, so the snippet for Scribe combines the cookbook call [E25] with the parameter list in the API reference [E24]; verify field names on first run (UNVERIFIED). To read the cost of each call: `client.text_to_speech.with_raw_response.convert(...)` and read the `character-cost` header [E31]. `voices.search()` lists voices [E29].

---

## 5. Azure AI Speech (ar-JO)

### Text-to-speech voices for ar-JO

| Voice | Gender | Type | HD / Dragon HD | Source |
|---|---|---|---|---|
| `ar-JO-SanaNeural` | Female | Standard neural | No | [M2] |
| `ar-JO-TaimNeural` | Male | Standard neural | No | [M2] |

- The voice table comes from the Microsoft Learn source file in Microsoft's docs repository on GitHub, because the live Learn page loads its TTS tab dynamically and the fetch returned only the speech-to-text tab [M2] [M3]. The rows show no style, role or multilingual notes.
- **No HD voice for ar-JO.** The HD voices page lists Dragon HD for six locales (de-DE, en-US, es-ES, fr-FR, ja-JP, zh-CN), HD Flash for zh-CN and en-US text, and Dragon HD Omni (hundreds of multilingual voices) without saying which locales it covers; no Arabic HD voice appears [M4]. Whether an Omni voice can speak Arabic: UNVERIFIED.
- Other Arabic neural voices exist for MSA-style narration, for example ar-SA `ZariyahNeural` (F) and `HamedNeural` (M), ar-EG `SalmaNeural` and `ShakirNeural`, ar-LB `LaylaNeural` and `RamiNeural`, ar-SY `AmanyNeural` and `LaithNeural` [M2].
- To list voices live: `GET https://{region}.tts.speech.microsoft.com/cognitiveservices/voices/list` and filter `Locale == "ar-JO"` [M37]. Whether the ar-JO voices render dialect-spelled Arabic well, or only MSA, is not documented (UNVERIFIED).

### Speech-to-text for ar-JO

| Mode | ar-JO | Notes | Source |
|---|---|---|---|
| Fast transcription | **Yes (explicit tick)** | Synchronous REST, `transcriptions:transcribe`, API version 2025-10-15, under 5 hours and under 500 MB; set `locales: ["ar-JO"]` for best accuracy; multiple locales trigger language identification. Python import path `azure.ai.transcription` (`TranscriptionClient`); pip package name not stated (UNVERIFIED). | [M1] [M5] |
| Real-time (Speech SDK) | Locale is in the table whose intro says it summarises real-time, fast and batch support, but the table has no per-mode column for real-time, so the tick is not individual (partly UNVERIFIED) | `azure-cognitiveservices-speech`; single-shot recognition stops after about 15 s (30 s in another quickstart), so use continuous recognition for stories | [M1] [M6] [M10] [M38] |
| Batch | Same caveat as real-time | REST (api-version 2024-11-15), `contentUrls` or a blob container, `timeToLiveHours` 6 h to 31 days | [M1] [M7] |
| Custom speech | Audio plus human-labelled transcript, plain text | No phrase list, output format or structured text for ar-JO (only ar-SA has those) | [M1] |
| Post-stream refinement | Not listed for ar-JO | Only ar-SA among Arabic locales | [M1] |
| MAI-Transcribe-2 | Arabic as `ar` only, **public preview, no SLA, not recommended for production** | `modelOptions.timestamps: "word"` | [M30] |

**Word-level timestamps.** Fast transcription: yes, each phrase has a `words` array with `offsetMilliseconds` and `durationMilliseconds` [M5]. Batch: set `wordLevelTimestampsEnabled: true` [M7]. Real-time Python: call `speech_config.request_word_level_timestamps()` (added in SDK 1.5.0); per-word offset and duration arrive on the `Recognized` event, not `Recognizing`; the Learn Python tab does not show how to read the per-word list, and the C# sample reads `Best()` then `Words` with `Word`, `Offset`, `Duration` (ticks of 100 ns) [M8] [M9]. No published accuracy figure for ar-JO (UNVERIFIED).

### Prices (USD, Azure Retail Prices API, region eastus or Global, seen 2026-10-17)

| Item | Price | Source |
|---|---|---|
| Speech-to-text, real-time standard ("S1 Speech To Text") | **$1.00 per audio hour** | [M13] |
| Fast transcription | **$0.36 per hour**. A separate "Fast Transcription Promo" meter at $0.10 per hour also exists; its terms and dates are unknown (UNVERIFIED). | [M15] |
| Batch transcription | **$0.18 per hour** | [M16] |
| Custom real-time STT / custom fast transcription | $1.20 / $0.45 per hour | [M13] [M15] |
| Neural TTS (standard voices such as SanaNeural) | **$15.00 per 1M characters** | [M14] |
| Neural HD TTS | $22.00 per 1M characters (no ar-JO HD voice) | [M14] |
| Personal Voice synthesis | $24.00 per 1M characters, plus voice storage $600 per 1,000 profiles ($0.60 each; the pricing page says per month) | [M17] |

### Free tier (F0)

- Speech-to-text: **5 audio hours free per month**, real-time only, shared between standard and custom; **batch not supported** on F0 [M12]. Whether fast transcription is available on F0 is unclear: the quotas page marks the fast-transcription limits "not applicable" for F0 (UNVERIFIED) [M11].
- Text-to-speech neural: **0.5 million characters free per month** [M12].
- F0 request limits (not adjustable): STT concurrency 1; TTS 20 transactions per 60 seconds; 10 minutes maximum audio per TTS request [M11]. Standard (S0) for comparison: STT 100 concurrent (adjustable), TTS 30 transactions per second default, fast transcription and batch 600 requests per minute, fast transcription up to 500 MB and 5 hours per file [M11].

### Azure voice cloning (not needed if ElevenLabs does the 3 clones)

Personal voice requires approval through Microsoft's limited-access intake form, an explicit recorded consent statement from the speaker, and a 5 to 90 second sample; the page says "more than 90 languages" without listing them and does not say whether Arabic or ar-JO output is supported, nor whether the feature is GA or preview [M35]. Treat Azure cloning as UNVERIFIED and unavailable by default.

---

## 6. Azure AI Foundry / Azure OpenAI models and Azure AI Translator

### Models offered (sold directly by Azure, per the model catalogue seen 2026-10-17) [M19]

GPT-6 family (`gpt-6-astra`, `gpt-6-sol`, `gpt-6-luna`, `gpt-6.1-sol`), GPT-5.6 (`sol`, `terra`, `luna`), `gpt-5.5`, `gpt-5.4` and `gpt-5.4-pro`, **`gpt-5.4-mini` and `gpt-5.4-nano`**, `gpt-5.2`, `gpt-5.1`, `gpt-5`, **`gpt-5-mini` and `gpt-5-nano`**, **`gpt-4.1`, `gpt-4.1-mini`, `gpt-4.1-nano`**, `gpt-4o` and `gpt-4o-mini`, the o-series, `gpt-oss-20b` and `gpt-oss-120b` (preview), plus a `gpt-chat-latest` preview. Several chat variants (gpt-5-chat and others) are already retired. Some GPT-6 and GPT-5.6 and 5.5 models need quota requests on some tiers. Other model collections (Mistral, DeepSeek, Grok, Llama, Cohere and others) are mentioned on a tab I did not read (UNVERIFIED). The catalogue says nothing Arabic-specific except that GPT-4o has "superior performance in non-English language tasks". **No primary source ranks these models on Arabic or Jordanian dialect**, so quality is UNVERIFIED; the price and limits below are solid, the Arabic quality needs a test on 5 real transcripts.

OpenAI itself positions GPT-5.4 nano for "classification, data extraction, ranking" (a fit for the labelling step) and GPT-5.4 mini as its efficient small model; it marks `gpt-5-mini` deprecated on its own API and points to `gpt-5.6-terra` for new balanced workloads [O1] [O2] [O3]. Azure still lists gpt-5-mini as current [M19].

### Prices, Global Standard, per 1M tokens (Azure Retail Prices API; short-context rows for GPT-5.6)

| Model | Input | Cached input | Output | Source |
|---|---|---|---|---|
| gpt-4.1-nano | $0.10 | $0.025 | $0.40 | [M24] |
| gpt-4.1-mini | $0.40 | $0.10 | $1.60 | [M23] |
| gpt-4.1 | $2.00 | not retrieved | not retrieved (UNVERIFIED) | [M27] |
| gpt-5.4-nano | $0.20 | $0.02 | $1.25 | [M22] (matches OpenAI [O2]) |
| gpt-5.4-mini | $0.75 | $0.075 | $4.50 | [M21] (matches OpenAI [O2]) |
| gpt-5.6-luna | $0.20 | $0.02 | $1.20 (long context $0.40 in / $1.80 out) | [M25] |
| gpt-5.6-terra | $2.00 | $0.20 | $12.00 | [M26] (matches OpenAI [O3]) |
| gpt-5-mini / gpt-5-nano / gpt-4o-mini | Global Standard rows not returned by my queries (UNVERIFIED); OpenAI direct lists gpt-5-mini at $0.25 in / $2.00 out | | | [O1] |

Data Zone deployments cost about 10% more than Global in the rows seen (gpt-4.1-mini $0.44 vs $0.40 input) [M23]. The Azure OpenAI pricing page itself shows "$-" placeholders and says GPT-6 Sol and Luna prices are "currently in processing for publishing" [M31]; no GPT-6 price is listed here.

### Quota and tier limits that matter

- Seven quota tiers exist: Free Tier and Tiers 1 to 6. The first tier is assigned from your current usage and relationship with Microsoft, and the system upgrades automatically as usage grows; a `NoAutoUpgrade` setting exists (preview) via the quotaTiers API. The page publishes **no Free Tier numbers** (UNVERIFIED) [M20].
- Tier 1 for the small models (Global Standard): gpt-5.4-mini 1,000 requests/min and 1,000,000 tokens/min; gpt-5.4-nano 5,000 and 5,000,000; gpt-4.1-mini 5,000 and 5,000,000 (6,000 and 6,000,000 on regional Standard); gpt-4.1-nano 5,000 and 5,000,000. For 30 stories these limits are not a constraint [M20].
- 30 Azure OpenAI resources per region per subscription, 32 standard deployments per resource [M20].
- Free trials and Azure for Students show "N/A" in the batch-quota columns; the page does not say whether a free-trial subscription can deploy chat models at all (UNVERIFIED) [M20].
- Spending: Azure free accounts get a spending limit equal to the credit (the docs' example is $200); when credits run out, deployed services are disabled for the rest of the billing period, and the limit cannot be set to a custom amount; pay-as-you-go subscriptions have no spending limit [M32]. The free-account page describes $200 of credit for 30 days in its metadata only [M34]. Azure budgets only notify and do not stop consumption; they are evaluated every 24 hours on cost data that arrives 8 to 24 hours late, and can call an action group (webhook or Azure Function) at subscription or resource-group scope [M33].

### Azure AI Translator

- Arabic is a single entry `ar` (no regional variants or dialects listed); it supports text and document translation, Custom Translator, transliteration, and is ticked for **LLM translation** [M28]. Whether it handles Jordanian-dialect source text is not documented (UNVERIFIED); the project's targets are English and MSA only, which is the easy case.
- Price: **S1 standard translation $10.00 per 1M characters** (Global), free F0 tier **2 million characters per month** [M18] [M29]. The pricing page shows "$-" placeholders; the $10 comes from the Retail Prices API.
- 30 stories of about 800 words is roughly 150,000 characters (assumption: about 6 characters per word including spaces), so $1.50 at S1 or $0 within F0. A small LLM costs about $0.10 to $0.60 for the same translation (see section 8) and gives control over tone and terminology, so use the LLM as primary and keep Translator as an optional deterministic cross-check or free fallback.

---

## 7. Price table

All USD, seen 2026-10-17.

| Provider | Item | Price | Source |
|---|---|---|---|
| ElevenLabs | Free plan | $0, 10k credits/month, no cloning, non-commercial | [E1] [E4] [E10] |
| ElevenLabs | Starter (minimum for IVC) | $6/month list; $1 first month promo "until Oct 18"; 30k credits | [E1] [E2] |
| ElevenLabs | Creator (adds Professional Voice Cloning) | $22/month; $11 first month; 121k credits | [E1] [E2] |
| ElevenLabs | Pro | $99/month; 600k credits | [E1] |
| ElevenLabs | Pay As You Go | Minimum top-up $5; credits expire after 12 months; service pauses at zero balance with no overage when auto top-up is off | [E5] |
| ElevenLabs | TTS: v4, v3, Multilingual v2 | $0.08 per 1K characters | [E2] |
| ElevenLabs | TTS: v4 Turbo, v3 Conversational, Flash v2.5 / Turbo | $0.04 per 1K characters | [E2] |
| ElevenLabs | Scribe v2 (and v2 Medical) | $0.22 per hour | [E2] |
| ElevenLabs | Scribe v2 Realtime | $0.39 per hour | [E2] |
| ElevenLabs | Instant voice clone creation | No separate price found (UNVERIFIED) | [E2] [E8] |
| Azure Speech | STT real-time standard | $1.00 per hour | [M13] |
| Azure Speech | STT fast transcription | $0.36 per hour ($0.10 promo meter exists, terms unknown) | [M15] |
| Azure Speech | STT batch | $0.18 per hour | [M16] |
| Azure Speech | Neural TTS (ar-JO voices) | $15 per 1M characters | [M14] |
| Azure Speech | Neural HD TTS | $22 per 1M characters | [M14] |
| Azure Speech | Personal Voice | $24 per 1M characters + $600 per 1,000 profiles | [M17] |
| Azure Speech | F0 free | 5 h real-time STT, 0.5M neural TTS characters per month | [M12] |
| Azure LLM | gpt-4.1-nano / 4.1-mini | $0.10 in, $0.40 out / $0.40 in, $1.60 out per 1M tokens | [M24] [M23] |
| Azure LLM | gpt-5.4-nano / 5.4-mini | $0.20 in, $1.25 out / $0.75 in, $4.50 out per 1M tokens | [M22] [M21] |
| Azure LLM | gpt-5.6-luna / 5.6-terra (short context) | $0.20 in, $1.20 out / $2.00 in, $12.00 out per 1M tokens | [M25] [M26] |
| Azure Translator | S1 text translation; F0 free | $10 per 1M characters; 2M characters per month free | [M18] [M29] |
| Azure account | Free account credit | $200 for 30 days (page metadata) | [M34] |

---

## 8. Budget arithmetic (question 7)

### Assumptions (mine; each is a stated assumption, not a documented fact)

- STT: 30 stories x 2 minutes = 60 minutes = **1.0 audio hour**.
- LLM: 4 passes per story (polish, translate, label, one retry); each pass about 3,000 input tokens and 3,000 output tokens (800 words at an assumed 3 tokens per Arabic word is about 2,400, plus prompt). Per story 12,000 in and 12,000 out; for 30 stories **360,000 in and 360,000 out**. The tokens-per-word ratio is UNVERIFIED.
- Narration: 1 minute is about 1,000 characters (ElevenLabs' own table equates 10,000 characters with about 10 minutes [E2]; Arabic density may differ, UNVERIFIED). 30 stories = 30,000 characters. Clone tests: 3 clones x 10 test lines x 300 characters = 9,000 characters. **Base TTS = 39,000 characters.**
- "Safe" case = every quantity x 3 (retries, voice A/B tests, model comparisons): 3 audio hours, 1.08M tokens each way, 117,000 characters.

### Unit costs

| Item | Base | Safe (x3) |
|---|---|---|
| ElevenLabs TTS v4 or Multilingual v2: characters x $0.08/1K | 39,000 -> $3.12 | 117,000 -> $9.36 |
| ElevenLabs TTS Flash v2.5: x $0.04/1K | $1.56 | $4.68 |
| ElevenLabs Scribe v2: hours x $0.22 | 1 h -> $0.22 | 3 h -> $0.66 |
| Azure fast transcription: hours x $0.36 | $0.36 | $1.08 |
| Azure neural TTS, stories only: characters x $15/1M | 30,000 -> $0.45 | 90,000 -> $1.35 |
| Azure personal voice (if approved): 3 x $0.60 + test chars x $24/1M | 1.80 + 0.216 = $2.02 | 1.80 + 0.648 = $2.45 |
| LLM gpt-4.1-nano: 0.36M x $0.10 + 0.36M x $0.40 | $0.18 | $0.54 |
| LLM gpt-4.1-mini: 0.36 x 0.40 + 0.36 x 1.60 | $0.72 | $2.16 |
| LLM gpt-5.4-nano: 0.36 x 0.20 + 0.36 x 1.25 | $0.52 | $1.57 |
| LLM gpt-5.4-mini: 0.36 x 0.75 + 0.36 x 4.50 = 0.27 + 1.62 | $1.89 | $5.67 |
| LLM gpt-5.6-luna: 0.36 x 0.20 + 0.36 x 1.20 | $0.50 | $1.51 |
| LLM gpt-5.6-terra: 0.36 x 2.00 + 0.36 x 12.00 = 0.72 + 4.32 | $5.04 | $15.12 |
| Azure fallback smoke test (5 stories ar-JO TTS = 5,000 chars x $15/1M = $0.075; 0.25 h STT x $0.36 = $0.09) | $0.17 | $0.33 |

For the totals below I use gpt-5.4-mini for every LLM step as the conservative choice. Using gpt-4.1-mini instead saves $1.17 (base) or $3.51 (safe).

### (a) ElevenLabs primary (TTS, clones, Scribe), Azure fallback and LLM

| | Base | Safe |
|---|---|---|
| ElevenLabs usage at API rates (v4 TTS + Scribe) | 3.12 + 0.22 = $3.34 | 9.36 + 0.66 = $10.02 |
| ElevenLabs plan: Starter $6 covers about $6 of API usage (the API-pricing page lists 75,000 v4 characters and 27 Scribe hours for Starter; $6 / $0.08 per 1K = 75,000 and $6 / $0.22 = 27.3, so the table is the plan fee converted at API rates) | usage $3.34 < $6, fits | usage $10.02 > $6, short by $4.02, so add the $5 minimum Pay As You Go top-up |
| **ElevenLabs cash** | **$6** ($1 if the first-month promo applies) | **$6 + $5 = $11** ($6 with promo) |
| Azure (credits): LLM gpt-5.4-mini + fallback smoke test | 1.89 + 0.17 = **$2.06** | 5.67 + 0.33 = **$6.00** |
| **Total** | **$8.06** | **$17.00** |

Using Flash v2.5 for iteration drafts instead of v4 brings Safe ElevenLabs usage to 4.68 + 0.66 = $5.34, inside the $6 plan, so cash stays $6.

### (b) Azure only (STT, LLM, TTS ar-JO; cloning via personal voice if approved)

| | Base | Safe |
|---|---|---|
| STT fast transcription | $0.36 | $1.08 |
| LLM gpt-5.4-mini | $1.89 | $5.67 |
| TTS neural ar-JO, stories | $0.45 | $1.35 |
| Cloning, personal voice (access-gated, Arabic unconfirmed) | $2.02 | $2.45 |
| **Total (all from Azure credits)** | **$4.72** | **$10.55** |

The F0 allowances (5 h real-time STT, 0.5M TTS characters) would zero out the STT and TTS lines if used; the table ignores them to stay conservative. Without cloning, (b) is $2.70 base and $8.10 safe.

### Is $25 enough?

**Yes, in every case.** Expected total is $8 (a, base) to $17 (a, safe); Azure-only is $5 to $10.5. The ElevenLabs cash part is $6 to $11 and Azure can be paid from credits, so the cash outlay is at most $11 even in the safe case. The budget breaks only if the LLM is a premium model: gpt-5.6-terra for all steps costs $15.12 in the safe case, which with (a) would reach about $26.5. Use the mini or nano tier and cap the larger models.

**Cheapest sensible plan:** one month of ElevenLabs Starter ($6, or $1 if the first-month promo applies to this account), run every ElevenLabs test inside that month (3 clones, narration of the 30 stories, a Scribe comparison), keep auto top-up off, cancel before renewal, and put all LLM, fallback TTS and fallback STT work on Azure credits. Azure-only is cheaper on paper, but the clone requirement cannot be guaranteed there.

---

## 9. Recommendation and spend-cap rules (question 8)

### Provider choice

| Step | Primary | Fallback | Reason |
|---|---|---|---|
| Speech-to-text with word timestamps | **Azure fast transcription with an explicit locale** (`ar-JO` for dialect stories, `ar-SA` or `ar` for MSA, `en-US` for English) | ElevenLabs Scribe v2 | The only provider with a documented ar-JO locale; its cost comes from credits, which keeps ElevenLabs cash for narration and cloning; word offsets are in the response. Scribe is cheaper per hour ($0.22 vs $0.36) and has a documented Arabic band but no dialect control. Run both on 3 real 2-minute clips (under $0.10 in total) and keep the winner as primary. |
| Polish, translate, label | **Azure gpt-5.4-mini or gpt-4.1-mini** for polish and translation, **gpt-5.4-nano or gpt-4.1-nano** for labelling | The other mini model | Cheapest tier with large rate limits; Arabic quality must be tested on 5 stories before locking in. Translator is an optional free fallback for English to MSA. |
| Narration | **ElevenLabs** (`eleven_v4` or `eleven_multilingual_v2`, chosen by listening test) using a Jordanian-accent voice from a clone, Voice Design or the library | Azure `ar-JO-SanaNeural` or `TaimNeural` | Documented accent control exists only on the voice side at ElevenLabs; Azure ar-JO is the guaranteed Jordanian-locale fallback, at $15 per 1M characters and free within F0. |
| Voice cloning (staff and opted-in storytellers) | **ElevenLabs IVC** (Starter), staff-only endpoint | None needed | Azure personal voice is access-gated with unconfirmed Arabic. |

One interface: `transcribe(audio, locale) -> words[{text, start_ms, end_ms}]`, `synthesize(text, language, voice_id) -> audio + cost`, `clone_voice(files, consent_id) -> voice_id` (Azure implementation raises NotSupported), `complete(step, text, target_lang) -> text + token usage`. Choose the provider per capability from config so either can be primary. Fall back only on auth, quota or 5xx errors, never on "quality", to avoid double charging.

### Spending-cap and caching rules for the code

1. **Ledger first.** Table `api_spend(provider, operation, units, est_usd, actual_usd, story_id, user_id, created_at)`. Before every paid call, compute `est_usd = units x rate x 1.25` from a `prices.yaml` copied from the price table with an `as_of` date, add it to the running total, and refuse with `BudgetExceeded` if the total would pass the cap. After the call, replace the estimate with the real figure (ElevenLabs `character-cost` header, Azure token usage and audio duration).
2. **Caps.** Global hard cap $22 of the $25 (keep $3 headroom); ElevenLabs cash cap $12 (Starter plus at most one $5 top-up); Azure internal cap equal to the credits you want to burn (suggest $10); per-story ceiling $0.60; warn at 70%, block non-staff calls at 85%, block everything at 100%. A `SPEND_FREEZE` environment flag turns every paid call into a cached-only call.
3. **Input limits.** Narration text at most 1,500 characters (staff override only); audio uploads at most 3 minutes; LLM input at most 1,200 words with `max_output_tokens` set (about 3,500); at most 2 regenerations per story; 3 clones in total during the test.
4. **Content-addressed caching.** STT key = sha256(audio) + provider + locale. LLM key = sha256(step + model + prompt_version + input text). TTS key = sha256(normalised text + provider + model + voice_id + settings + output_format); store the audio file and serve it to all listeners. Never call a provider for a key that exists. Pre-generate the demo stories and serve them from cache.
5. **Cheap by default.** Iterate with Flash v2.5 or Azure F0; use v4 only on an explicit "final render". When splitting long text, pass `previous_text` and `next_text` so prosody stays continuous [E18].
6. **No retry storms.** At most one retry on 429 or 5xx, with backoff; ElevenLabs concurrency on Starter is low, so queue requests.
7. **Provider-side backstops.** ElevenLabs: keep Pay As You Go auto top-up off (at zero balance service pauses with no overage) [E5]; create a dedicated API key restricted to the endpoints you use, with its own credit quota and an IP allowlist [E34]; turn on the credit-usage email at a chosen percentage [E33]. Azure: put the work on a credit-type subscription with its spending limit (services are disabled when credits run out) [M32]; set a modest tokens-per-minute value on each deployment as a velocity brake [M20]; add a budget with an action group that disables the key, but do not rely on it because evaluation lags by 8 to 24 hours [M33]. The in-app ledger is the real cap.
8. **Consent record per clone.** Store person, date, scope, withdrawal contact and the ElevenLabs `voice_id`; delete the clone when consent is withdrawn.

---

## UNVERIFIED list

ElevenLabs
1. Whether the Free plan can call the TTS, Scribe or voice APIs at all (implied, never stated). Cloning on Free is documented as unavailable.
2. The body text of the Prohibited Use Policy (only headings, the Unauthorized Use of Voice reporting route and general enforcement text were retrievable); what it says specifically about consent and impersonation.
3. Whether an in-app recorded IVC sample is treated differently from an uploaded one (no documented difference).
4. When `requires_verification` is true for an API-created clone and how to complete it from code.
5. Whether the Starter first-month $1 promo applies to this owner, whether "Until Oct 18" is inclusive, and that $6 is the renewal price (read from the API-pricing page).
6. Credits consumed per character by API model and plan (the dollar rates are documented; credit rates are not), and whether creating an IVC clone consumes credits.
7. Whether any Voice Library voice tagged Jordanian exists and is usable on Starter through the API (only non-primary Famulor lists two); allowed values of the `accent` filter.
8. Which ElevenLabs model sounds best for Arabic (no Arabic benchmark published).
9. Scribe accuracy for Jordanian or any Levantine dialect (only an overall Arabic "Good" band, WER above 10% up to 20%); the Arabic marketing page is stale and inconsistent.
10. Maximum Scribe file size (3 GB in one page, 5 GB in another); file-size limit for IVC samples.
11. Python return type of `text_to_speech.convert` and exact `speech_to_text.convert` response field names (not shown in the README).
12. Voice Design prompt wording for Jordanian Arabic and which plans include Voice Design.

Azure
13. The ar-JO voice list comes from Microsoft's docs repository on GitHub because the live Learn TTS tab did not load; whether Dragon HD Omni voices can speak Arabic; whether the ar-JO neural voices handle dialect-spelled text or only MSA.
14. Whether ar-JO real-time and batch transcription are individually supported (only fast transcription has an explicit tick); fast transcription availability on F0; published ar-JO accuracy.
15. Terms and dates of the "Fast Transcription Promo" meter at $0.10 per hour.
16. Azure prices come from the Retail Prices API list prices (eastus, eastus2 or Global), because the pricing pages show "$-" placeholders; regional and Data Zone prices differ (Data Zone about 10% higher in the rows seen). Global Standard prices for gpt-5-mini, gpt-5-nano, gpt-4o-mini, and gpt-4.1 output were not retrieved; Azure prices for GPT-6 models are not published yet.
17. Free Tier quota numbers; whether a free-trial subscription can deploy chat models; how the Azure credits the owner holds apply to model deployments.
18. Arabic and Jordanian-dialect quality of every candidate LLM; the tokens-per-word and characters-per-minute assumptions used in the arithmetic.
19. Azure Translator handling of Jordanian-dialect source text; Azure personal voice approval, Arabic output support and GA status; pip package name for the fast-transcription client; Azure collections beyond Azure OpenAI (Mistral, DeepSeek, Grok, Llama, Cohere) not read.

---

## Sources index (all seen 2026-10-17)

ElevenLabs (primary)
- [E1] https://elevenlabs.io/pricing
- [E2] https://elevenlabs.io/pricing/api
- [E3] https://elevenlabs.io/docs/overview/models
- [E4] https://elevenlabs.io/docs/overview/administration/billing.md
- [E5] https://elevenlabs.io/docs/overview/administration/pay-as-you-go.md
- [E6] https://elevenlabs.io/docs/eleven-creative/voices/voice-cloning/instant-voice-cloning.md
- [E7] https://elevenlabs.io/docs/eleven-api/concepts/voice-cloning.md
- [E8] https://elevenlabs.io/docs/api-reference/voices/ivc/create
- [E9] https://elevenlabs.io/docs/cookbooks/voices/instant-voice-cloning and https://elevenlabs.io/docs/eleven-api/guides/how-to/voices/instant-voice-cloning.md
- [E10] https://elevenlabs.io/terms-of-use
- [E11] https://elevenlabs.io/use-policy
- [E12] https://elevenlabs.io/docs/help-center/product/voices/voice-cloning/are-there-any-restrictions-on-what-voices-i-can-upload-for-voice-cloning
- [E13] https://elevenlabs.io/safety
- [E14] https://elevenlabs.io/docs/eleven-creative/voices/voice-library.md
- [E15] https://elevenlabs.io/docs/help-center/product/voices/voice-library/why-cant-i-use-some-voices-from-the-voice-library.md
- [E16] https://elevenlabs.io/docs/help-center/product/core-capabilities/text-to-speech/how-do-i-select-the-language-and-accent.md
- [E17] https://elevenlabs.io/docs/help-center/product/core-capabilities/text-to-speech/what-languages-can-the-ai-speak.md
- [E18] https://elevenlabs.io/docs/overview/capabilities/text-to-speech.md
- [E19] https://elevenlabs.io/docs/overview/capabilities/text-to-speech/eleven-v4.md
- [E20] https://elevenlabs.io/docs/eleven-api/choosing-the-right-model.md
- [E21] https://elevenlabs.io/docs/eleven-creative/voices/voice-design.md
- [E22] https://elevenlabs.io/docs/api-reference/voices/voice-library/get-shared
- [E23] https://elevenlabs.io/docs/overview/capabilities/speech-to-text.md
- [E24] https://elevenlabs.io/docs/api-reference/speech-to-text/convert
- [E25] https://elevenlabs.io/docs/eleven-api/guides/cookbooks/speech-to-text.md
- [E26] https://elevenlabs.io/speech-to-text/arabic
- [E27] https://elevenlabs.io/docs/help-center/product/core-capabilities/speech-to-text/how-many-speech-to-text-requests-can-i-make-and-can-i-increase-it.md
- [E28] https://pypi.org/project/elevenlabs/
- [E29] https://github.com/elevenlabs/elevenlabs-python
- [E30] https://elevenlabs.io/docs/eleven-api/quickstart.md
- [E31] https://elevenlabs.io/docs/api-reference/introduction.md
- [E32] https://elevenlabs.io/docs/api-reference/text-to-speech/convert
- [E33] https://elevenlabs.io/docs/overview/administration/account
- [E34] https://elevenlabs.io/docs/overview/administration/workspaces/api-keys.md
- [E35] https://elevenlabs.io/docs/eleven-api/resources/errors.md
- [E36] https://elevenlabs.io/docs/help-center/product/voices/voice-cloning/why-does-my-voice-or-accent-not-sound-correct-after-cloning.md
- [E37] https://elevenlabs.io/docs/help-center/product/core-capabilities/text-to-speech/which-voices-in-the-voice-library-are-native-to-a-specific-language.md
- [E38] https://elevenlabs.io/docs/help-center/account/general/is-there-a-limit-to-how-many-credits-i-can-use-at-once.md
- [E39] https://elevenlabs.io/docs/help-center/product/core-capabilities/text-to-speech/how-much-does-it-cost-to-generate-using-eleven-v3-alpha.md
- [E40] https://elevenlabs.io/text-to-speech/arabic
- [E41] https://elevenlabs.io/docs/llms.txt and https://elevenlabs.io/docs/llms-full.txt (searched for a plain free-plan API statement; none found)

Non-primary (aggregator, used only to find a lead; every fact from it is labelled)
- [F1] https://www.famulor.io/voices/elevenlabs/languages/ar
- [F2] https://www.famulor.io/voices/elevenlabs/languages/ar/accents/jordanian

Microsoft (primary)
- [M1] https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support?tabs=stt
- [M2] https://github.com/MicrosoftDocs/azure-ai-docs/blob/main/articles/ai-services/speech-service/includes/language-support/tts.md (Microsoft's docs source repository)
- [M3] https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support?tabs=tts (TTS tab did not load)
- [M4] https://learn.microsoft.com/en-us/azure/ai-services/speech-service/high-definition-voices
- [M5] https://learn.microsoft.com/en-us/azure/ai-services/speech-service/fast-transcription-create
- [M6] https://learn.microsoft.com/en-us/azure/ai-services/speech-service/get-started-speech-to-text
- [M7] https://learn.microsoft.com/en-us/azure/ai-services/speech-service/batch-transcription-create
- [M8] https://learn.microsoft.com/en-us/azure/ai-services/speech-service/get-speech-recognition-results
- [M9] https://learn.microsoft.com/en-us/python/api/azure-cognitiveservices-speech/azure.cognitiveservices.speech.speechconfig
- [M10] https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-to-text
- [M11] https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-services-quotas-and-limits
- [M12] https://azure.microsoft.com/en-us/pricing/details/cognitive-services/speech-services/ and https://azure.microsoft.com/en-us/pricing/details/speech/ (F0 allowances only; prices show "$-")
- [M13] https://prices.azure.com/api/retail/prices?$filter=armRegionName eq 'eastus' and contains(meterName,'Speech To Text') and priceType eq 'Consumption'&currencyCode=USD
- [M14] https://prices.azure.com/api/retail/prices?$filter=armRegionName eq 'eastus' and contains(meterName,'Neural') and priceType eq 'Consumption'&currencyCode=USD
- [M15] https://prices.azure.com/api/retail/prices?$filter=armRegionName eq 'eastus' and contains(meterName,'Fast') and priceType eq 'Consumption'&currencyCode=USD
- [M16] https://prices.azure.com/api/retail/prices?$filter=armRegionName eq 'eastus' and contains(meterName,'Speech to Text') and priceType eq 'Consumption'&currencyCode=USD
- [M17] https://prices.azure.com/api/retail/prices?$filter=contains(meterName,'Personal Voice')&currencyCode=USD
- [M18] https://prices.azure.com/api/retail/prices?$filter=productName eq 'Azure Translator'&currencyCode=USD
- [M19] https://learn.microsoft.com/en-us/azure/ai-foundry/foundry-models/concepts/models-sold-directly-by-azure
- [M20] https://learn.microsoft.com/en-us/azure/ai-foundry/openai/quotas-limits (and https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/quota)
- [M21] https://prices.azure.com/api/retail/prices?$filter=armRegionName eq 'eastus2' and contains(skuName,'5.4 mini')&currencyCode=USD
- [M22] https://prices.azure.com/api/retail/prices?$filter=armRegionName eq 'eastus2' and contains(skuName,'5.4 nano')&currencyCode=USD
- [M23] https://prices.azure.com/api/retail/prices?$filter=armRegionName eq 'eastus2' and contains(skuName,'4.1 mini')&currencyCode=USD
- [M24] https://prices.azure.com/api/retail/prices?$filter=armRegionName eq 'eastus2' and contains(skuName,'nano')&currencyCode=USD
- [M25] https://prices.azure.com/api/retail/prices?$filter=armRegionName eq 'eastus2' and contains(skuName,'5.6 luna')&currencyCode=USD
- [M26] https://prices.azure.com/api/retail/prices?$filter=armRegionName eq 'eastus2' and contains(skuName,'5.6 terra ShortCo')&currencyCode=USD
- [M27] https://prices.azure.com/api/retail/prices?$filter=armRegionName eq 'eastus2' and contains(skuName,'gpt 4.1 Inp glbl')&currencyCode=USD
- [M28] https://learn.microsoft.com/en-us/azure/ai-services/translator/language-support
- [M29] https://azure.microsoft.com/en-us/pricing/details/cognitive-services/translator/
- [M30] https://learn.microsoft.com/en-us/azure/ai-services/speech-service/mai-transcribe
- [M31] https://azure.microsoft.com/en-us/pricing/details/azure-openai/
- [M32] https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/spending-limit
- [M33] https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-acm-create-budgets
- [M34] https://azure.microsoft.com/en-us/pricing/free-services/
- [M35] https://learn.microsoft.com/en-us/azure/ai-services/speech-service/personal-voice-overview
- [M37] https://learn.microsoft.com/en-us/azure/ai-services/speech-service/rest-text-to-speech
- [M38] https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-recognize-speech

OpenAI (primary, cross-check of model prices and positioning only)
- [O1] https://developers.openai.com/api/docs/models/gpt-5-mini
- [O2] https://openai.com/index/introducing-gpt-5-4-mini-and-nano/
- [O3] https://developers.openai.com/api/docs/models/gpt-5.6-terra
