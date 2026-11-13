// SmartResume – datengetriebenes Template.
// Alle Inhalte kommen aus data.json (von render.py erzeugt). Texte werden als
// Strings eingefügt und NICHT als Typst-Markup interpretiert – Sonderzeichen
// wie # * _ $ @ // in Lebensläufen können das Layout daher nicht zerstören.

#let data = json("data.json")
#let accent = rgb(data.accent)
#let ink = rgb("#111111")
#let muted = rgb("#555555")
#let L = data.labels
#let P = data.person

#set document(title: data.doc_title, author: P.name, keywords: data.doc_keywords)
#set text(font: data.font, lang: "de", fill: ink, size: 10pt, weight: 400)

// Fügt Text ein und verlinkt das Wort "Portfolio" (falls URL vorhanden)
#let linkify(s) = {
  if data.portfolio_url == "" or not s.contains("Portfolio") { return s }
  let parts = s.split("Portfolio")
  for (i, p) in parts.enumerate() {
    p
    if i < parts.len() - 1 {
      link(data.portfolio_url)[#text(fill: accent, weight: 600)[Portfolio]]
    }
  }
}

#let links-row(size: 9pt) = {
  if data.show_links and data.links.len() > 0 {
    set text(size: size, fill: accent)
    data.links.map(l => link(l.url)[
      #box(height: 11pt, baseline: 20%)[#image("icons/" + l.icon + ".svg", height: 11pt)]
      #h(4pt)#l.label
    ]).join(h(24pt))
  }
}

// ─────────────────────────────────────────────
// Seite 1: Deckblatt
// ─────────────────────────────────────────────
#page(paper: "a4", margin: 0pt)[
  #place(top + left, rect(width: 100%, height: 58%,
    fill: gradient.linear(rgb("#EFEFEF"), white, dir: ttb)))
  #place(top + left, rect(width: 100%, height: 8pt, fill: accent))

  #align(center)[
    #v(if data.photo != "" { 2cm } else { 5cm })
    #if data.photo != "" {
      box(width: 7cm, height: 7cm, radius: 3.5cm, clip: true,
        image(data.photo, width: 100%, height: 100%, fit: "cover"))
      v(0.5cm)
    }
    #text(size: 34pt, weight: 600)[#P.name]
    #v(8pt)
    #line(length: 4cm, stroke: 1.5pt + accent)
    #v(8pt)
    #text(size: 10pt, weight: 600, fill: accent, tracking: 0.5pt)[#upper(L.application_as)]
    #v(4pt)
    #box(width: 75%)[
      #set par(justify: false)
      #set text(hyphenate: false)
      #text(size: 14pt, weight: 600)[#data.job_title]
    ]
  ]

  #place(bottom + left, pad(left: 3cm, right: 3cm, bottom: 2.5cm)[
    #if data.summary != "" [
      #text(size: 10pt, weight: 600, fill: accent, tracking: 0.5pt)[#upper(L.about)]
      #v(10pt)
      #rect(width: 100%, inset: (x: 16pt, y: 14pt), fill: white,
        stroke: (left: 3pt + accent))[
        #set par(leading: 1.0em, justify: false)
        #text(size: 11pt, fill: rgb("#222222"))[#data.summary]
      ]
      #v(16pt)
    ]
    #align(center)[
      #text(size: 9pt, fill: muted)[
        #(P.contact_line)
      ]
      #v(8pt)
      #links-row()
    ]
  ])
  #place(bottom + left, rect(width: 100%, height: 8pt, fill: accent))
]

// ─────────────────────────────────────────────
// Seite 2: Anschreiben (DIN 5008 angelehnt)
// ─────────────────────────────────────────────
#let CL = data.cover_letter
#page(paper: "a4", margin: (top: 2.5cm, bottom: 2cm, left: 2.5cm, right: 2cm))[
  #set text(size: 10.5pt)
  #set par(leading: 0.9em, justify: true)

  #align(center)[#text(size: 9.5pt)[#P.sender_line]]
  #v(36pt)

  // Empfänger
  #block[
    #set par(justify: false, leading: 0.65em)
    #text(weight: 600)[#CL.company]
    #for line in CL.recipient_lines [ \ #line ]
  ]
  #v(14pt)
  #align(right)[#data.date_line]
  #v(16pt)
  #text(weight: 600)[#CL.subject]
  #v(12pt)
  #CL.salutation
  #for p in CL.paragraphs {
    v(8pt)
    par(linkify(p))
  }
  #v(18pt)
  #L.closing
  #v(4pt)
  #if data.signature != "" {
    image(data.signature, height: 1.4cm)
    v(2pt)
  } else {
    v(14pt)
  }
  #P.name
]

// ─────────────────────────────────────────────
// Seite 3: Lebenslauf
// ─────────────────────────────────────────────
#set page(paper: "a4", margin: 0.5in)
#set par(justify: true)
#set text(size: 10.5pt, ligatures: false)
#show link: set text(fill: accent)

#let section(title) = {
  v(10pt)
  block(below: 10pt)[
    #text(size: 12pt, weight: 600, fill: accent)[#smallcaps(title)]
    #v(-6pt)
    #line(length: 100%, stroke: 1pt)
  ]
}

#let entry(title, right-top, subtitle, right-bottom) = {
  grid(columns: (1fr, auto), column-gutter: 8pt,
    text(weight: 600, size: 10.5pt)[#title], align(right, text(size: 10pt)[#right-top]))
  v(2pt)
  grid(columns: (1fr, auto), column-gutter: 8pt,
    text(size: 10pt, fill: muted)[#subtitle], align(right, text(size: 10pt, fill: muted)[#right-bottom]))
  v(2pt)
}

// „Lebenslauf“ groß, darunter Name und Kontakt in einer grauen Zeile – der Name steht damit weiter als Text oben,
// so erkennt jedes Bewerbersystem auch einen einzeln hochgeladenen Lebenslauf.
#text(size: 20pt, weight: 700)[#L.cv]
#v(-7pt)
#text(size: 9pt, fill: muted)[#(P.name, P.contact_line).filter(x => x != "").join("  ·  ")]
// Links als lesbarer Text (Symbole allein kann Bewerber-Software nicht lesen)
#if data.show_links and P.links_line != "" [
  #v(-6pt)
  #text(size: 9pt, fill: muted)[#P.links_line]
]

#if data.experience.len() > 0 {
  section(L.experience)
  for job in data.experience {
    entry(job.role, job.dates, job.company, job.location)
    list(..job.bullets)
    v(6pt)
  }
}

#if data.education.len() > 0 {
  section(L.education)
  for e in data.education {
    entry(e.institution, e.dates, e.degree, e.location)
    if e.detail != "" { list(e.detail) }
    v(6pt)
  }
}

#if data.skills.len() > 0 {
  section(L.skills)
  set text(hyphenate: false, size: 9.5pt)
  set par(justify: false)
  grid(columns: (3.6cm, 1fr), row-gutter: 8pt, column-gutter: 10pt,
    ..data.skills.map(s => (text(weight: 600)[#s.category], [#s.items])).flatten())
}
