# OmniVoice (k2-fsa) as a free narration and voice-cloning option for Hikaya

Researched 2026-10-21. Every page cited below was opened on that date ("seen 2026-10-21"). Source ids like [P2] or [N1] resolve to a URL in the Source index at the bottom. Primary sources are the GitHub repository, the Hugging Face model card and the arXiv paper ([P...] ids). Community pages ([N...] ids, for example the omnivoice.cpp port) are the project's own pages but are NOT primary for OmniVoice itself, so every fact taken from them is labelled non-primary. Pages were read through a summarising fetch tool, so quotes are short and anything load-bearing (above all the licence text) should be re-read in a browser before you rely on it. Anything I could not confirm from a primary source is marked UNVERIFIED and repeated in the list near the end.

## Summary and recommendation

1. What it is: OmniVoice is a text-to-speech and voice-cloning model (about 0.6B parameters, diffusion-language-model-style, 600+ languages, released April 2026 by the k2-fsa team; code copyright Xiaomi Corp.); it is not a speech-recognition model.
2. Licence blocks it as a main provider: the code is Apache-2.0 but the pretrained weights are CC-BY-NC (non-commercial), and the maintainers say in writing that the weights cannot be used commercially; the bundled audio tokenizer adds a separate Boson licence with a 100,000-user threshold.
3. Arabic is listed but not Jordanian: the official language list has 21 Arabic rows (Standard Arabic 1,483.5 h of training data, "Levantine Arabic" only 15.65 h) and no Jordanian, Palestinian, Syrian or Lebanese row; the only Arabic numbers are automatic ones (WER on a 24-language set, CER on FLEURS) and I found no dialect evaluation, no listening test and no statement about diacritics.
4. Running it: Python API is simple (`pip install omnivoice`, PyTorch, 3 to 10 s reference plus transcript, 24 kHz output); there is no official server or Docker image; GPU speed is excellent (RTF about 0.03 on a datacentre GPU) but CPU speed is only claimed by a community server (RTF about 4.9, so roughly 5 minutes per minute of audio).
5. Recommendation: (a) ignore it for the demo build; spend 10 minutes (and 0 USD) on a listening test on the official Hugging Face Space, and only if Jordanian-accent output clearly passes add it as an off-by-default optional third provider (b), labelled "non-commercial, demo only"; do not make it primary (c).

---

## 1. What OmniVoice is

| Item | Finding | Source |
|---|---|---|
| Type | A **text-to-speech model with voice cloning and voice design**. The README and model card call it a "massively multilingual zero-shot text-to-speech (TTS) model" and list voice cloning, voice design (gender, age, pitch, style, accent) and inline tags such as laughter. It is **not** a speech-recognition model; Whisper is only used on the side to transcribe the reference clip when you do not supply its text. | [P2] [P17] [P25] |
| Size | Hugging Face reports **0.6B parameters** (safetensors total 612,577,288); base model Qwen/Qwen3-0.6B. The paper's Table 1 says **0.8B**; its table note defines that figure as the whole voice-cloning system including the audio tokenizer, and the Higgs audio tokenizer is listed at 0.2B on its own Hugging Face page, so 0.6B + 0.2B is the likely reason for the gap (my inference, the paper does not explain it). Downloaded repo storage about 3.27 GB. | [P19] [P17] [P27] [P29] [P21] |
| Architecture (one sentence) | A bidirectional Transformer initialised from Qwen3-0.6B that maps text directly to 8-codebook acoustic tokens (Higgs audio tokenizer) with a non-autoregressive "diffusion language model" style iterative unmasking (the paper uses 32 steps by default; 16 steps are also reported), with no separate text-to-semantic stage and no grapheme-to-phoneme step. | [P25] [P26] |
| Training data | 581k hours aggregated from 50 open datasets, 646 languages. | [P4] [P26] |
| Release date | Hugging Face repo created **2026-03-30**; arXiv v1 submitted **2026-04-01** (v3 on 2026-04-21); first PyPI release 0.1.0 on **2026-04-02**; latest PyPI release 0.2.1 on **2026-07-16**. The GitHub repo creation date itself was not shown (UNVERIFIED), so the April 2026 dates above are the best primary evidence. | [P19] [P25] [P31] [P8] |
| Maintainer | The **k2-fsa** GitHub organisation; paper authors Han Zhu (who answers the issues as "zhu-han"), Lingxuan Ye, Wei Kang, Zengwei Yao, Liyong Guo, Fangjun Kuang, Zhifeng Han, Weiji Zhuang, Long Lin and Daniel Povey. The LICENSE file carries "Copyright 2026 Xiaomi Corp." | [P2] [P25] [P3] |
| Related names | omnivoice.cpp is a C++/GGML port by a different author (ServeurpersoCom). It is **not** in the official list of community projects (that list names audio.cpp, MLX ports, omnivoice-server and others). Treat it as unofficial. | [N1] [P6] |

---

## 2. Licence

| Component | Licence | Source |
|---|---|---|
| Code (GitHub, PyPI) | **Apache-2.0** (LICENSE file, "Copyright 2026 Xiaomi Corp."; PyPI agrees). | [P3] [P31] |
| Pretrained weights | **CC-BY-NC (non-commercial).** The Hugging Face card says the code is Apache 2.0 and "the pre-trained model is licensed under the CC-BY-NC due to constraints from its training data (e.g., Emilia)". | [P18] [P17] |
| Audio tokenizer shipped inside the repo | A separate **Boson Higgs Audio 2 Community License** (file `audio_tokenizer/LICENSE`, based on the Meta Llama 3 community licence): limited royalty-free grant; if your products exceed **100,000 annual active users** you must get an expanded licence from Boson, which Boson may refuse; a "Built with Higgs Materials licensed from Boson AI USA, Inc." notice and "Higgs Audio 2" naming rules when you distribute; no use of the materials or their outputs to improve other large language models; acceptable-use rules incorporated from Meta's policy. The standalone Hugging Face page of that tokenizer shows "License: other" and asks commercial users to email Boson. | [P20] [P21] |

Points that matter for Hikaya:

- **Trap:** the Hugging Face front-matter and the Hugging Face API show **no licence tag at all**, the GitHub sidebar and PyPI show Apache-2.0, and the README on GitHub has no licence section. Someone who only looks at those will think the model is Apache. The model card body text is the only place the weights licence appears, and the maintainer has said so in discussions. [P19] [P18] [P2] [P3]
- **Maintainer statements (primary).** Hugging Face discussion #29 (3 July, year not shown on the page): "We have updated the model's license to CC-BY-NC." Discussion #37: "the model weights are non-commercial and can't be used commercially"; Emilia has a CC-BY-4.0 part and a CC BY-NC 4.0 part and other training sets such as WenetSpeech-Yue are also non-commercial. GitHub issue #258: the licence "does not allow any commercial usage" and there is "currently no commercially usable checkpoint", with a plan to release one but no date. GitHub issue #235: a new model on commercial-safe data (Emilia-YODAS, CC BY 4.0) is planned under a "more open license", no confirmed timeline, and even then the Higgs tokenizer's 100,000-user rule still applies. [P23] [P24] [P10] [P11]
- **Non-profit use is not answered.** Issue #262 (an airport's non-profit public-service kiosk asking for authorisation) got only the general "we cannot grant commercial licences" reply. So whether a one-off, unpaid demo is acceptable is **my reading, not the maintainers' answer**: it is plausibly inside "non-commercial", but any paid, sponsored, sold or investor-facing use is not. This is not legal advice; UNVERIFIED. [P12]
- **Voice-cloning restriction.** The README disclaimer says users are "strictly prohibited" from using the model for unauthorised voice cloning, voice impersonation, fraud, scams or other illegal or unethical use, and the developers accept no liability. Consent-based cloning of team members fits that; cloning anyone without consent does not. [P2]
- **Non-primary warning.** The omnivoice.cpp README and one GGUF model card (Supbatomic) say the upstream model is "Apache 2.0". That contradicts the primary sources above; the port author's own GGUF card (Serveurperso) is tagged `cc-by-nc-4.0` and says the GGUF files "carry the same non commercial terms". Do not rely on the Apache claims. [N1] [N3] [N2]

---

## 3. Arabic

### What the primary sources say

- **README.** No Arabic variant or dialect is named. The only "Arabic" in the README is the tip to write **Arabic numerals** (digits like 123) out as words, which is about digits, not the Arabic language. The only dialects named in the README are Chinese (Sichuan, Shaanxi) and English accents (American, British) for voice design, and it warns that voice design "is trained on Chinese and English data only". So **voice design cannot be used to ask for a Jordanian accent.** [P2]
- **Language list (`docs/languages.md`, 646 languages, 581k hours).** It contains these 21 Arabic rows (training hours in the last column). The table has no row called Jordanian, Palestinian, Syrian, Lebanese, Iraqi (as such), or "Modern Standard Arabic" by that name; the closest are **"Standard Arabic"** and **"Levantine Arabic"**. [P4]

| Language (as listed) | ID | Hours |
|---|---|---|
| Standard Arabic | arb | 1483.53 |
| Najdi Arabic | ars | 203.54 |
| Moroccan Arabic | ary | 104.67 |
| Gulf Arabic | afb | 98.55 |
| Egyptian Arabic | arz | 23.23 |
| Hijazi Arabic | acw | 22.32 |
| Omani Arabic | acx | 22.03 |
| Tunisian Arabic | aeb | 21.63 |
| Libyan Arabic | ayl | 20.13 |
| **Levantine Arabic** | apc | **15.65** |
| North Mesopotamian Arabic | ayp | 10.92 |
| Baharna Arabic | abv | 10.41 |
| Sudanese Arabic | apd | 9.93 |
| Algerian Arabic | arq | 9.64 |
| Saidi Arabic | aec | 9.28 |
| Judeo-Moroccan Arabic | aju | 7.21 |
| Mesopotamian Arabic | acm | 3.78 |
| Chadian Arabic | shu | 2.29 |
| Algerian Saharan Arabic | aao | 2.02 |
| Eastern Egyptian Bedawi Arabic | avl | 1.86 |
| Dhofari Arabic | adf | 0.31 |

- **Jordanian data is in the training list by name only.** The paper's Appendix A lists, among the Arabic training sets, "Arabic datasets found from [37] (darija speech to text, DarijaTTS-clean, Jordan-Audio, UAE 100K)", plus MGB-2/3/5, SADA, MASC, Mixat, ClArTTS and ArVoice. The paper does not say how much of it was used or which language row it feeds. A community-side description (non-primary: the Habibi Arabic TTS paper that [37] points to) says Jordan-Audio is Levantine, 4.9 hours, 4,016 utterances. So the Jordanian material is at most a few hours inside a 15.65-hour Levantine row; whether the two numbers are linked is UNVERIFIED (my inference). [P28] [P29] [N7]
- **Published numbers for Arabic (all automatic, no human listening score).** In the paper's MiniMax-Multilingual-24 table (Table 3) the Arabic row is: word error rate OmniVoice 1.392, MiniMax 1.665, ElevenLabs 1.666 (lower is better); speaker similarity (SIM-o) OmniVoice 0.776, MiniMax 0.736, ElevenLabs 0.706. On FLEURS (Appendix C, Table 10) "Standard Arabic" has character error rate 2.58 for the real recordings and 1.92 for OmniVoice, measured with the Omnilingual ASR model. The paper has no Arabic-dialect evaluation. Which Arabic variety the 24-language test set uses is not stated in what I read (UNVERIFIED), and a low error rate measures whether an ASR can read the words back, not whether the accent sounds Jordanian. [P26] [P27] [P28] [P29]
- **Listening samples.** The demo page has a language selector with a "Standard Arabic" label, but I could not see an Arabic sample table (UNVERIFIED whether samples exist). The official Hugging Face Space is running on ZeroGPU and says you enter text, pick a language and optionally upload a reference recording; the language dropdown contents were not visible to me. [P32] [P33]
- **Diacritics (tashkeel).** No primary source says OmniVoice needs, uses or ignores tashkeel. The paper says the model uses the subword tokenizer of a pre-trained LLM, with no grapheme-to-phoneme step and no language-specific text normalisation, which suggests plain text goes straight in, but how undiacritised Jordanian text is voiced is **UNVERIFIED**. [P26]
- **Language argument.** In the Python API `language` accepts a name or a code, or `None` for language-agnostic mode, and the docstring says "Performance is slightly better if you specify the language". So for Jordanian text the natural trials are `"Levantine Arabic"` (`apc`) and `"Standard Arabic"` (`arb`); I did not test which works. [P7]

### Community evidence (non-primary)

- A Hugging Face discussion with a third-party engineering benchmark (English, German, Modern Standard Arabic, Spanish, Mandarin) reports only a five-language mean (speaker cosine 0.707, 0.0% ASR error, RTF 0.45 for an int8 build, hardware not stated) and no Arabic-only numbers. [N9]
- "Lahgtna" (oddadmix) is a community **fine-tune** of OmniVoice for Arabic dialects. Its card lists checked dialects (Egypt, Saudi Arabia, Morocco, Iraq, Sudan, Palestine, Lebanon, Syria, Libya, Tunisia, Bahrain, Yemen, Algeria) and **Jordan only as planned**; says diacritised input improves pronunciation; shows no licence tag and no evaluation numbers. That a dialect fine-tune exists suggests the base model's dialect coverage is thin, but that is my inference, not a finding. [N6]
- The silma-ai Arabic TTS benchmark Space compares MSA, Egyptian and Saudi voices; I could not see that it includes OmniVoice. [N8]

---

## 4. Voice cloning

| Question | Finding | Source |
|---|---|---|
| Reference length | Use a clip of **3 to 10 seconds**; longer audio slows generation and may reduce cloning quality. The paper's speed test used a 3-second prompt. | [P2] [P26] |
| Transcript of the reference | **Recommended** (`ref_text`). If omitted, the library loads Whisper to transcribe it automatically (device selectable, CPU allowed). A user report on GitHub (issue #246) says similarity and pronunciation were weak with reference audio only and acceptable with the transcript; that is one unconfirmed user report. The omnivoice.cpp port requires a WAV plus its transcript (or a pre-encoded `.rvq` file) (non-primary). | [P2] [P15] [N1] |
| Reusing a voice | `create_voice_clone_prompt(...)` builds a reusable prompt that can be saved and loaded (added in release 0.2.1), so a team member's voice needs to be encoded once. | [P2] [P8] |
| Speak Arabic text from an Arabic or other-language reference | The README says: for standard pronunciation use a reference **in the same language as the target text**; in cross-lingual cloning "the generated speech will carry an accent from the reference audio's language". So an Arabic reference with Arabic text is the supported case; an English-speaking reference reading Arabic text will sound accented. The paper reports no cross-lingual cloning results. | [P2] [P27] |
| Would a Jordanian reference carry a Jordanian accent? | **UNVERIFIED.** No primary source tests it. Indirect hints: the cross-lingual accent note above, and a tip that a Sichuan-dialect reference gives more stable Sichuan-dialect output (a Chinese example, not Arabic). Risks: only 15.65 hours of "Levantine Arabic" training data, no Jordanian label, and my expectation (inference) that text written in Modern Standard Arabic will be pronounced as Modern Standard Arabic even in a Jordanian voice, so the text itself probably has to be written in dialect. Voice design cannot help. Test this, do not assume it. | [P5] [P2] [P4] |
| Consent | The README prohibits unauthorised cloning but the software has no consent mechanism that I could find (UNVERIFIED for the whole code base). Keep Hikaya's own written consent record per person. | [P2] |

---

## 5. Running it

### Hardware and speed

| Item | Finding | Source |
|---|---|---|
| Minimum VRAM | **Not stated** in the README or model card. Evidence from users only: a GitHub issue says the current model is "about 2GB" and runs on a 16 GB RTX 5060 Ti; another reporter runs on an RTX 3050 with 8 GB VRAM and 16 GB RAM; a Hugging Face user reports 1.3 GB VRAM plus 2.4 GB system RAM after quantising and offloading, and VRAM spikes to 8 GB without that. All are user claims, not benchmarks. | [P13] [P16] [N9] |
| Supported devices | NVIDIA CUDA (README example `torch 2.8.0+cu128`, `dtype=torch.float16`), Apple Silicon (`device_map="mps"`), Intel Arc GPUs (`xpu`; tested on Arc A310 4 GB and Arc Pro B50 16 GB). The README mentions CPU only for the Whisper transcription step. In the code, the audio tokenizer is placed on the CPU when the model runs on MPS because it does not support MPS. **CPU-only inference of the main model is not documented in any primary source.** | [P2] [P7] |
| GPU speed | Paper: real-time factor (RTF) **0.0319** at 16 steps, batch 1, on an H20 GPU (0.0598 at 32 steps), about 0.022 with larger batches. README: "as low as 0.025". A 3-second prompt and 10-second outputs were used. | [P26] [P27] [P2] |
| CPU speed | Only a community server (omnivoice-server, non-primary) says "RTF ~4.92 on CPU, ~0.2 on GPU" (hardware not given) and that MPS is "broken on Apple Silicon (use CPU instead)". RTF 4.92 means about 4.9 seconds of compute per second of audio, i.e. roughly **5 minutes to narrate 1 minute** on whatever CPU they used. Treat as an order of magnitude only. | [N5] |
| omnivoice.cpp on CPU or Apple Silicon | The port (MIT, non-primary) runs on CPU, CUDA, ROCm, Metal and Vulkan, with backend chosen automatically or forced with `GGML_BACKEND`. GGUF sizes: Q8_0 about 656 MB model + 289 MB tokenizer, Q4_K_M about 407 MB + 252 MB, F32 2.46 GB + 734 MB. **Neither its README nor its GGUF card gives any speed or RTF number**, and it ships no releases (123 commits, 200 stars, 13 open issues when seen). Speed on a laptop CPU or Apple Silicon is UNVERIFIED. | [N1] [N2] [N4] |

### Install and API

- **Install:** install PyTorch for your hardware first, then `pip install omnivoice` (PyPI 0.2.1, Python 3.10 or newer). Optional extras: `omnivoice[tn]` for number/date/currency normalisation (needs `pynini`, which on macOS must come from conda). A fresh virtual environment is recommended. First run downloads the weights from Hugging Face. [P2] [P31] [P17]
- **Python API:** `OmniVoice.from_pretrained("k2-fsa/OmniVoice", device_map=..., dtype=torch.float16)` then `model.generate(text=..., language=..., ref_audio=..., ref_text=..., speed=..., duration=..., num_step=...)`; it returns a list of NumPy arrays at 24 kHz. Command-line tools: `omnivoice-infer`, `omnivoice-infer-batch`, and a Gradio demo `omnivoice-demo`. [P2] [P7]
- **Server or Docker:** the official repo has **no server and no Docker image**. The maintainer wrote in issue #251 that "we do not have an official implementation for serving" and, in issue #246, that the model "does not support true streaming inference". Community options (all non-primary, all unofficial): `omnivoice-server` (MIT, OpenAI-style `/v1/audio/speech`, Dockerfiles and compose files, "Early Development Notice", 89 stars, no concurrency mentioned and a user says it lacks it); omnivoice.cpp `tts-server` (OpenAI-compatible, cloned-voice registry, no Docker); vLLM-Omni (a user says it drops `instruct`, `duration` and `num_step`). [P14] [P15] [N5] [N1] [P6]

### Realistic effort to wrap it in FastAPI inside Docker Compose (my estimate, not from sources)

- **Thin Python wrapper** (load the model once at start-up, one `/tts` and one `/clone` endpoint, cache the saved voice prompt per consenting speaker, encode WAV to MP3 with ffmpeg, queue requests one at a time): about half a day to one day for someone who knows FastAPI.
- **Docker on a laptop:** an NVIDIA laptop needs the NVIDIA container toolkit and a CUDA image, about another half day. A CPU-only container works in principle but is slow (see RTF above). I expect, but did not verify, that a Docker container on macOS cannot use the Apple GPU (UNVERIFIED), which would push you to run it natively on the host as a side service.
- **Demo risk:** an extra multi-gigabyte model, a new failure mode (dropped words, cut-off sentence ends: section 6) and a slow path if no GPU. For a one-off demo, pre-rendering the narration is safer than live generation.

---

## 6. Safeguards, quality problems and maturity

- **Safeguards.** The README and model card carry only the usage disclaimer quoted in section 2; **no watermarking** is mentioned in the README, the model card, or the main model source file I read. I did not audit the rest of the code, so watermarking elsewhere is UNVERIFIED. The paper text I retrieved has no ethics statement; but its HTML table of contents (as summarised) lists an "Ethics Statements" and a "Limitations and Future Works" appendix whose text I could not retrieve, while the PDF text had only Appendices A to D, so this is UNVERIFIED. [P2] [P17] [P7] [P27] [P29]
- **Arabic issues.** None of the visible open-issue titles mention Arabic (the GitHub search URL was blocked by robots rules, and I did not see the closed list), so "no Arabic issues exist" is UNVERIFIED. The closest are #268 (a request for better dialect accuracy, about Sichuan, not Arabic) and one Hugging Face thread (#30, the third-party five-language benchmark). [P9] [P13] [N9]
- **General quality problems reported by users in open GitHub issues (not confirmed by maintainers):** voice cloning sometimes drops parts of the input text (#253, no fix); audio often cut off at sentence ends (#245); inconsistent speaking speed within one generation (#248); click or pop at the start of cloned audio (#256); pronunciation of numbers, dates, emails and URLs is poor without the optional normaliser (#246, the maintainer says it is a text-normalisation front-end problem); unstable pronunciation across generations (#237); "random voice on each call" in auto-voice mode (#255). On Hugging Face, users also report an odd sound on full stops and the tail of the reference clip leaking into the start of the output (discussion #12). The tips file adds that outputs of about 1 to 2 seconds may be unreliable without reference audio. [P9] [P15] [P16] [P5] [N9]
- **Stated maturity.** README: cloning "is the most stable mode"; other uses "may produce unstable results for some low-resource languages or edge cases". PyPI version 0.2.1 (eight releases from 2 April to 16 July 2026), no "Development Status" classifier. Popular: 1.58k likes and about 1.94M downloads last month on Hugging Face. The open-issue count is UNVERIFIED (my two fetches gave 39 and 26). [P2] [P31] [P8] [P17] [P9]

---

## 7. Recommendation

**Choose (a) for the demo build: do not integrate OmniVoice now. Run the 10-minute test below; promote to (b) only on a clear pass. Never (c).**

Reasoning:

1. **Licence rules out (c) and limits (b).** The weights are non-commercial, the maintainers say so repeatedly, and there is no commercial checkpoint yet. A one-off, unpaid demo is plausibly fine, but Hikaya's own roadmap (a product) cannot rest on it. A future commercial-safe checkpoint is planned with no date, and the Boson tokenizer licence still applies.
2. **Fit with the core requirement is unproven.** Hikaya needs a Jordanian-accented voice. OmniVoice lists Standard Arabic strongly (1,483 h) but "Levantine Arabic" only at 15.65 h, has no Jordanian label, cannot design an accent, and has no published dialect or listening evaluation. Its Arabic automatic scores look good on a 24-language test, but those say little about accent.
3. **The money saved is small.** Your earlier research note in this repo (`speech-voice-and-llm.md`, summary item 4) puts the whole ElevenLabs cash cost at about $6 to $11 inside the $25 budget, with Azure ar-JO neural voices as the coded fallback. OmniVoice would save a few dollars while adding a model download, a new serving path and demo risk.
4. **Hardware is a gamble on a laptop.** On a modest GPU it is fast; on CPU the only figure (community, non-primary) is roughly 5 minutes per minute of audio, and the C++ port has no published speed numbers.
5. **It still deserves one cheap look**, because if a Jordanian reference does carry the accent, a free, offline, consent-friendly option is valuable as an off-by-default third provider behind the same provider interface.

### Cheapest sensible test: a 10-minute listening test (cost: 0 USD, no code)

1. **Prepare (2 min).** Write 3 sentences of 15 to 25 words each: one in written Jordanian dialect (about a heritage story), one in Modern Standard Arabic, one in English. Take one 5 to 10 second clean clip from a **consenting** Jordanian team member and type its exact transcript. The Space is a public hosted app, so do not upload anyone's voice who has not agreed to that.
2. **Generate (5 min).** Open the official Space (Hugging Face `k2-fsa/OmniVoice`; if it is queued or sleeping, use the Colab notebook linked from the README instead). For each sentence generate (i) with the language set to the nearest Arabic entry (try the Levantine and the Standard Arabic options for the dialect sentence), no reference; (ii) cloned from the Jordanian clip with its transcript. That gives about 6 to 8 short clips; also generate the same dialect sentence once with Azure ar-JO or ElevenLabs for comparison.
3. **Score (3 min).** Two or three Jordanian listeners rate each clip 1 to 5 for "sounds Jordanian", "every word correct" (also count mispronounced words), "sounds like the speaker" and "artefacts" (dropped words, cut-off endings, clicks).
4. **Pass bar (suggested, my numbers).** Promote to (b) only if the cloned dialect clip scores at least 4 of 5 for accent from most listeners, has at most one mispronounced word per about 20, no dropped words, and is not clearly worse than the paid provider. Otherwise stay at (a).
5. **If it passes**, add it as an optional provider (off by default, UI label "non-commercial demo only") using the Python API in an in-process module, pre-render narration instead of generating live, and keep ElevenLabs and Azure as the defaults.

The Space's language dropdown contents and quota behaviour are UNVERIFIED.

---

## UNVERIFIED list

1. Whether a Jordanian-accent reference audio carries a Jordanian accent into generated Arabic speech (no primary test exists).
2. Whether the training set "Jordan-Audio" (4.9 h Levantine per the non-primary Habibi paper) is part of the 15.65 h "Levantine Arabic" row, and how much Jordanian speech the model actually saw.
3. Whether OmniVoice needs or benefits from diacritics (tashkeel); no primary source says.
4. Whether the demo page has Arabic listening samples, and what the Hugging Face Space language dropdown contains.
5. Which Arabic variety the 24-language test set (Table 3) uses; there is no human (MOS) evaluation or dialect evaluation in what I read.
6. The paper's limitations and ethics text: fetches conflicted (HTML table of contents lists Appendices E and F, PDF text lists only A to D).
7. Watermarking anywhere in the code (only the main model file and the README/model card were checked).
8. Minimum VRAM and any CPU-only speed in a primary source; the CPU RTF of about 4.92 comes from a community server with unstated hardware; omnivoice.cpp has no published speed; Apple Silicon (Metal) speed is unknown.
9. Whether a one-off, unpaid demo is legally "non-commercial" under CC-BY-NC for this use (the maintainers' non-profit case, issue #262, got no direct answer); not legal advice.
10. Whether any open or closed GitHub issue mentions Arabic (issue search was blocked), and the exact open-issue count (39 versus 26 in two fetches).
11. Whether omnivoice.cpp accepts Arabic language names or codes (its README only shows English) and how well the port's quantised weights match the original; the port's README claims Apache for the weights, which contradicts the primary sources.
12. The GitHub repository creation date (April 2026 dates come from Hugging Face, arXiv and PyPI).
13. Whether Docker on macOS can use the Apple GPU, and my effort estimates in section 5 (judgement, not sourced).
14. The 0.6B versus 0.8B parameter gap explanation (my inference).
15. Exact quotes: all pages were read through a summarising tool; re-read the licence section of the Hugging Face model card and the Boson licence in a browser before relying on them.

---

## Source index (all seen 2026-10-21)

Primary sources:

- [P1] GitHub repository page: https://github.com/k2-fsa/OmniVoice
- [P2] README (raw): https://raw.githubusercontent.com/k2-fsa/OmniVoice/master/README.md
- [P3] LICENSE (Apache-2.0, Copyright 2026 Xiaomi Corp.): https://raw.githubusercontent.com/k2-fsa/OmniVoice/master/LICENSE
- [P4] Supported languages (646, with hours): https://raw.githubusercontent.com/k2-fsa/OmniVoice/master/docs/languages.md (rendered: https://github.com/k2-fsa/OmniVoice/blob/master/docs/languages.md)
- [P5] Tips: https://raw.githubusercontent.com/k2-fsa/OmniVoice/master/docs/tips.md
- [P6] Community projects list: https://raw.githubusercontent.com/k2-fsa/OmniVoice/master/docs/community-projects.md
- [P7] Main model source (`generate`, language argument, device handling): https://raw.githubusercontent.com/k2-fsa/OmniVoice/master/omnivoice/models/omnivoice.py
- [P8] GitHub releases: https://github.com/k2-fsa/OmniVoice/releases
- [P9] GitHub open issues list: https://github.com/k2-fsa/OmniVoice/issues (and page 2: https://github.com/k2-fsa/OmniVoice/issues?page=2)
- [P10] Issue #258 (commercial licence): https://github.com/k2-fsa/OmniVoice/issues/258
- [P11] Issue #235 (commercial licence, YODAS plan, Higgs 100k users): https://github.com/k2-fsa/OmniVoice/issues/235
- [P12] Issue #262 (non-profit authorisation question): https://github.com/k2-fsa/OmniVoice/issues/262
- [P13] Issue #268 (dialect accuracy and VRAM request): https://github.com/k2-fsa/OmniVoice/issues/268
- [P14] Issue #251 (no official serving): https://github.com/k2-fsa/OmniVoice/issues/251
- [P15] Issue #246 (pronunciation, no streaming, latency): https://github.com/k2-fsa/OmniVoice/issues/246
- [P16] Issue #253 (dropped text): https://github.com/k2-fsa/OmniVoice/issues/253
- [P17] Hugging Face model card: https://huggingface.co/k2-fsa/OmniVoice
- [P18] Hugging Face README (raw, front-matter and License section): https://huggingface.co/k2-fsa/OmniVoice/raw/main/README.md
- [P19] Hugging Face model API (createdAt, parameter total, no licence field): https://huggingface.co/api/models/k2-fsa/OmniVoice
- [P20] Audio tokenizer licence (Boson Higgs Audio 2 Community License): https://huggingface.co/k2-fsa/OmniVoice/raw/main/audio_tokenizer/LICENSE
- [P21] Higgs audio tokenizer page ("License: other", 0.2B): https://huggingface.co/bosonai/higgs-audio-v2-tokenizer
- [P22] Hugging Face discussion list: https://huggingface.co/k2-fsa/OmniVoice/discussions
- [P23] Discussion #29 (licence changed to CC-BY-NC): https://huggingface.co/k2-fsa/OmniVoice/discussions/29
- [P24] Discussion #37 (weights non-commercial): https://huggingface.co/k2-fsa/OmniVoice/discussions/37
- [P25] arXiv abstract: https://arxiv.org/abs/2604.00688
- [P26] arXiv HTML v1: https://arxiv.org/html/2604.00688v1
- [P27] arXiv HTML v3: https://arxiv.org/html/2604.00688v3
- [P28] arXiv PDF v2: https://arxiv.org/pdf/2604.00688v2
- [P29] arXiv PDF v3: https://arxiv.org/pdf/2604.00688v3
- [P30] Hugging Face paper page: https://huggingface.co/papers/2604.00688
- [P31] PyPI: https://pypi.org/project/omnivoice/
- [P32] Demo page: https://zhu-han.github.io/omnivoice
- [P33] Official Hugging Face Space: https://huggingface.co/spaces/k2-fsa/OmniVoice

Community and third-party (non-primary for OmniVoice; used for the port, speed claims and Arabic fine-tunes):

- [N1] omnivoice.cpp (C++/GGML port, MIT): https://github.com/ServeurpersoCom/omnivoice.cpp (README: https://raw.githubusercontent.com/ServeurpersoCom/omnivoice.cpp/master/README.md)
- [N2] GGUF weights by the port author (tagged cc-by-nc-4.0): https://huggingface.co/Serveurperso/OmniVoice-GGUF
- [N3] GGUF weights by another user (claims Apache): https://huggingface.co/Supbatomic/OmniVoice-GGUF
- [N4] omnivoice.cpp issues: https://github.com/ServeurpersoCom/omnivoice.cpp/issues
- [N5] omnivoice-server (community HTTP server, CPU RTF claim): https://github.com/maemreyo/omnivoice-server
- [N6] Lahgtna Arabic-dialect fine-tune: https://huggingface.co/oddadmix/lahgtna-omnivoice-v2
- [N7] Habibi Arabic TTS paper (dataset hours for Jordan-Audio): https://arxiv.org/html/2601.13802v1
- [N8] silma-ai Arabic TTS benchmark Space: https://huggingface.co/spaces/silma-ai/opensource-arabic-tts-benchmark
- [N9] Hugging Face community threads: #30 https://huggingface.co/k2-fsa/OmniVoice/discussions/30 ; #20 https://huggingface.co/k2-fsa/OmniVoice/discussions/20 ; #12 https://huggingface.co/k2-fsa/OmniVoice/discussions/12 ; #10 https://huggingface.co/k2-fsa/OmniVoice/discussions/10 ; #22 https://huggingface.co/k2-fsa/OmniVoice/discussions/22
- Search-result pages (used only to find the primary sources above, no facts taken): web searches for "OmniVoice k2-fsa arXiv", "omnivoice.cpp", "github k2-fsa OmniVoice issue Arabic", "Habibi unified-dialectal Arabic speech synthesis".
