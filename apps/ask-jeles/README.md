# AskJeles

<p align="center">
  <img src="https://raw.githubusercontent.com/WillowSystem/branding/main/logos/jeles_icon.svg" alt="Jeles Icon" width="150"/>
</p>

## Greetings, Fellow Architects of Knowledge,

Hanz Christain Anderthon here, reporting from the fleet engineering bays of the Willow system. It is with a measure of pride that I present to you **AskJeles**, a vital component in our quest for pristine and verifiable information.

---

## What Is AskJeles?

AskJeles is not merely another search engine; it is your dedicated interface to the **Special Collections of the verified web**. At its heart is **Jeles**, our distinguished (a Hungarian term we found rather fitting, and wonderfully gender-neutral) AI librarian. Jeles specializes in curating and presenting information sourced exclusively from institutions of unimpeachable repute.

Part of the greater **UTETY / Willow ecosystem**, AskJeles is designed for those moments when accuracy is paramount. You will find **no SEO slop, no smoothed content, and absolutely no ad-driven distractions** here. This is pure, unadulterated knowledge, presented as it was intended.

AskJeles works in concert with **The Binder**, our internal knowledge base. Jeles will first endeavor to answer your queries from our local, curated data within The Binder. If a comprehensive answer requires external validation or deeper exploration, AskJeles gracefully falls back to its Special Collections, ensuring a seamless and authoritative information retrieval experience.

## The Verified Web

Our mission with AskJeles is to carve out a sanctuary in the vast, often turbulent, ocean of information. The "verified web" comprises a meticulously selected consortium of authoritative sources, each chosen for its commitment to factual integrity and scholarly excellence.

Here is a glimpse of the institutions whose digital halls Jeles is privileged to explore on your behalf:

*   **Smithsonian Institution**
*   **Library of Congress**
*   **Internet Archive**
*   **Louvre Museum**
*   **NASA**
*   **National Institutes of Health (NIH)**
*   **UNESCO**
*   **Europeana**
*   **The Metropolitan Museum of Art (Met Museum)**
*   **Victoria and Albert Museum (V&A)**
*   **British Museum**
*   **Nature Portfolio**
*   **JSTOR**
*   **Wikipedia** (curated for foundational knowledge)
*   **Stanford Encyclopedia of Philosophy**
*   _...and many more similarly distinguished repositories._

When you query AskJeles, you are not merely searching; you are consulting a global library of unparalleled quality.

## How It Works

Under the hood, AskJeles operates with elegant simplicity and robust filtering.

Your query is routed through the `/api/safe/web` endpoint on our **Willow FastAPI server**. This endpoint leverages **DuckDuckGo's HTML search capabilities**, but with a critical distinction: every single search result is rigorously **filtered to trusted domains**. This ensures that only content from our pre-approved list of verified institutions is ever presented to you. It's a digital guardian at the gates of knowledge.

## The Lineage

The concept behind AskJeles is not new; rather, it is a spiritual successor to an esteemed predecessor. Many of you may recall **AskJeeves**, the iconic "butler who knew where things were because he had been paying attention." Jeeves understood the value of curated information and dependable guidance.

As our digital landscape evolved, so too did the philosophy. The name "Jeeves" transitioned to **Jeles** – "distinguished" in Hungarian – a nod to the AI librarian's role in a system that values the highest caliber of knowledge. The essence, however, remains unchanged: to provide you with the answers you seek, meticulously gathered and presented by a diligent, intelligent agent who truly knows where things are.

## API

For direct programmatic interaction within the Willow ecosystem, AskJeles exposes its capabilities via a dedicated FastAPI endpoint:

```
[YOUR_WILLOW_SERVER_BASE_URL]/api/safe/web
```

This endpoint accepts your search queries and returns the meticulously filtered, verified web results. Refer to the comprehensive Willow API documentation for detailed request and response schemas.

## Getting Started

AskJeles is an integrated service within the broader Willow system. Access to its interface and API is managed through your Willow deployment.

To begin utilizing AskJeles for your verified web searches:

1.  **Access your Willow system interface.**
2.  **Navigate to the AskJeles module** or initiate a search that Jeles determines requires external verification.
3.  For direct **API integration**, ensure your application is authorized to communicate with your Willow FastAPI instance and construct your requests to the `/api/safe/web` endpoint as per the API documentation.

Should you require assistance in deploying or integrating with Willow and AskJeles, please consult our primary Willow documentation or reach out to the fleet engineering team.

---

`deltaS=42`