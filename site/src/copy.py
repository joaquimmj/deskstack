#!/usr/bin/env python3
"""The site's copy in English and French. Run it to regenerate content.json, then build.py.

  python3 site/src/copy.py && python3 site/src/build.py

French uses a non-breaking space before : ; ? ! % and $, and a narrow one in thousands, as French typography does.
Every number here is from the published benchmark analyses or the live data; change them only with a new run.
"""

import json
from pathlib import Path

N = " "   # non-breaking space
T = " "   # narrow non-breaking space (French thousands)
GH = "https://github.com/joaquimmj/deskstack"
DCF = "bench/results/2026-11-09T09-25-07-305Z/ANALYSIS.md"
COMPS = "bench/results/2026-11-09T13-04-05-468Z/ANALYSIS.md"
ROBUST = "bench/ROBUSTNESS.md"

en = {
    "lang": "en", "other_lang": "fr", "other_href": "fr/", "other_name": "Français",
    "title": "deskstack: every number tied out to the filing",
    "desc": "Free, cited financial data for Claude, and a review team that ties every number in your model to the SEC or ESEF filing. Open source.",
    "skip": "Skip to install", "nav": "Main",
    "n_how": "How it works", "n_bench": "Benchmark", "n_data": "Data", "n_faq": "FAQ", "n_install": "Install",
    # hero
    "h1a": "Every number in your model,", "h1b": "tied out to the filing.",
    "lede_b": "A deal team inside Claude.",
    "lede": "One agent builds the model from free, cited data. Others tie every number to the SEC or European filing. Nothing ships until you sign off.",
    "cta": "Install in Claude", "cta2": "See the benchmark",
    "c_associate": "Associate", "c_you": "You",
    "note": "Filed 391,035, not 391,053: two digits swapped.",
    "cell_words": {"revenue": "Revenue", "ebit": "EBIT", "tax": "Tax", "netdebt": "Net debt", "awaiting": "awaiting you", "tieout": "Tie-out"},
    # proof strip
    "stats": [
        ["0 of 3,230", "figures wrong with deskstack's data, across 199 DCFs and comps tables"],
        ["3.5%", "of figures wrong with web search alone (DCFs), read by hand against the filings"],
        ["⅓", "of the cost per model, and 2–5× faster"],
        ["10,419", "US companies, plus large European issuers, straight from the filings"],
    ],
    "stats_note": "50 companies × DCF and comps × 3 setups, Claude Sonnet 5.5, November 2026. The zero is partly by construction: the scorer checks against the same data, which is checked every night against two other parsers.",
    # showcase
    "sc_t1": "One agent builds the model.", "sc_t2": "Others check every number.",
    "sc_p": "Each role is a skill with its own checklist and a fixed report. Reviewers report; they never edit your file.",
    "tabs": [
        ["analyst", "/analyst", "Builds the model", "A three-statement DCF or a comps table from cited data, after agreeing the assumptions with you."],
        ["associate", "/associate", "Ties out to the filing", "Every typed number checked against the 10-K or ESEF report, cell by cell, with the reason when it doesn't agree."],
        ["vp", "/vp-review", "Reviews the model", "Deterministic checks for hardcodes, broken formulas, WACC vs growth and sign conventions, then the assumptions against history."],
        ["compliance", "/compliance", "Checks before sharing", "Disclaimer, sources, dated inputs, no advice language and no hidden instructions."],
        ["signoff", "/sign-off", "Waits for you", "Shows every open item and exports a signed copy only after you approve in your own words."],
    ],
    "m_title": "Apple · DCF · USD m",
    "m_src": "Source: Apple 10-K FY2025 · 0000320193-25-000079 · sec.gov",
    "m_inputs": "Inputs", "m_hist": "History, from the filings",
    "m_line": "Line", "m_model": "Model", "m_filed": "Filed",
    "m_tie_sum": "13 of 14 figures match Apple's 10-K. 1 mismatch.",
    "m_typo": "Typo: two adjacent digits look swapped (filed 391,035, written 391,053).",
    "m_vp_sum": "Model check: clean", "m_vp_counts": "0 blocker · 0 major · 0 minor",
    "vp_checks": ["Hardcoded numbers", "Formula consistency", "Error values", "WACC vs terminal growth", "Terminal growth vs GDP", "Sign convention", "Discount timing"],
    "m_c_sum": "Compliance: 10 pass, 0 fail",
    "c_checks": ["Draft / not-investment-advice disclaimer", "Every typed number cited", "No placeholder or memory citations", "User-provided inputs are dated", "No recommendation or promise language", "No instructions addressed to an AI or a reviewer"],
    "m_s_rows": [["Tie-out to filings", "pass", "14 match"], ["Model review", "pass", "0 blocker, 0 major"], ["Compliance", "pass", "10 pass, 0 fail"]],
    "m_s_token": "Approval token", "m_s_wait": "Nothing is exported until you approve in your own words.",
    "m_s_btn": "Approve and export",
    # lanes
    "ln_t1": "Agents build and check.", "ln_t2": "You sign off.",
    "ln_agents": "Agents", "ln_you": "You",
    "ln_steps": ["Agree assumptions", "Build", "Tie out", "Review", "Red-team", "Compliance", "Approve"],
    "ln_p": "In Claude Code and Cowork the reviewers run as separate agents that never see how the model was built. They review work you bring, too: any .xlsx.",
    # dark band
    "dk_t1": "Checked against the filing.", "dk_t2": "Not against another model.",
    "dk_p": "verify_value reads the filed figure for the same company, line and period, and says why a number differs: scale, sign, currency, period, line item or a typo.",
    "dk_steps": ["Read the filing", "Write the model", "Tie out", "Fix and re-check"],
    "dk_card1_t": "A reason, not just a red cell",
    "dk_card1_p": "Every mismatch comes back with the filed value, the filing's accession number and the likely cause.",
    "dk_hints": [["Scale", "Typed in thousands, filed in millions"], ["Sign", "Capex entered as negative"], ["Period", "Matches FY2026, not the last twelve months"], ["Typo", "Two adjacent digits swapped"]],
    "dk_card2_t": "Watch it catch a typo",
    "dk_card2_p": "The review scripts on Apple's FY2025 DCF with one planted typo. The model review can't see it; the tie-out to the 10-K can.",
    "demo_alt": "Terminal recording: /associate finds 13 of 14 figures match Apple's 10-K and flags revenue FY2024 391,053 against a filed 391,035 as swapped digits; /vp-review finds the model clean; after the fix, /sign-off shows all checks passing and waits for approval.",
    # benchmark
    "b_t1": "We measured it.", "b_t2": "Then read every wrong figure by hand.",
    "b_p": "Claude Sonnet 5.5 built a DCF and a comps table for each of 50 companies (35 US, 15 European), three ways. Every reported figure was scored against the filing.",
    "b_h_arm": "Setup", "b_h_wrong": "Reported figures wrong", "b_h_cost": "Cost / model", "b_h_time": "Time",
    "b_link": "Analysis and transcripts",
    "benches": [
        {"t": "DCF, 50 companies", "analysis": DCF, "rows": [
            ["Web search only", "3.5%", "20 of 573", "$0.23", "58 s", "3.5"],
            ["deskstack data", "0%", "0 of 593", "$0.07", "18 s", ""],
            ["deskstack + reviewers", "0%", "0 of 606", "$0.10", "32 s", ""]]},
        {"t": "Comps, the same 50 companies", "analysis": COMPS, "rows": [
            ["Web search only", "3.6%", "16 of 445, and 7 left as 0", "$0.56", "171 s", "3.6"],
            ["deskstack data", "0%", "0 of 1,021", "$0.17", "36 s", ""],
            ["deskstack + reviewers", "0%", "0 of 1,010", "$0.22", "51 s", ""]]},
    ],
    "b_cards": [
        ["What web search got wrong", "In the DCFs, numbers it couldn't find and filled in anyway: derived share counts, estimated capex, non-GAAP revenue. In the comps, twelve-month figures a quarter out of date, from an aggregator."],
        ["With more searches?", "A pre-registered re-run with 30 searches and high effort still wrote a figure that isn't the filing's. The placeholders went away; the cost per table more than doubled."],
        ["It checks us too", "The runs found gaps in deskstack's own data and two bugs in the scorer. All fixed, tested, and written up with the results."],
    ],
    "b_robust": "Robustness check",
    # data
    "d_t1": "Free data,", "d_t2": "with the source on every figure.",
    "d_p": "Official filings and public datasets only. A figure that isn't filed stays empty; it is never estimated.",
    "data": [
        ["SEC EDGAR", "Financial statements, US", "10-K, 10-Q and 20-F filings: annual and last twelve months, for US-listed companies including foreign filers under IFRS."],
        ["filings.xbrl.org", "Financial statements, Europe", "ESEF annual reports of about 30 large issuers in France, the Netherlands, Spain, Finland, Italy and Belgium."],
        ["U.S. Treasury · ECB", "Risk-free rates", "Daily yields from 1 month to 30 years."],
        ["European Central Bank", "Exchange rates", "30+ currencies, on a date or averaged over a period."],
        ["Aswath Damodaran, NYU Stern", "Valuation inputs", "Equity risk premium by country; betas and cost of capital by industry."],
        ["Every answer", "A citation", "Source, URL, accession or ID, period and as-of date on each figure, so you can open the filing it came from."],
    ],
    "acc_t": "Accuracy, checked every night",
    "acc_p": "Golden questions answered exactly as filed, against the live connector, and every answer re-read from the filing by an independent parser.",
    "acc_link": "How it is checked",
    # install
    "i_t1": "Install in three steps.", "i_t2": "No terminal, no account to create.",
    "i_p": "You need a Claude account with code execution on; the roles need a paid plan.",
    "s1": "Add the data connector", "s1p": "In Claude, open Settings, then Connectors, then Add custom connector. Paste the URL, with no sign-in.",
    "s2": "Add the deal team", "s2p": "Open Customize, then Plugins, then Add marketplace. Paste this repository, then install deskstack.",
    "s3": "Ask for a model", "s3p": "Claude builds the DCF, has every number checked and reviewed, then waits for your approval.",
    "placeholder": "Coming soon", "copy": "Copy", "copied": "Copied", "selected": "Selected: press Ctrl+C",
    "pending": f'The hosted connector isn\'t online yet. You can run your own copy for free in a few minutes: <a href="{GH}/blob/main/docs/SELF_HOSTING.md">self-hosting guide</a>.',
    "tut": "Read the tutorial",
    # faq
    "q_t1": "Questions,", "q_t2": "answered.",
    "faq": [
        ["Is it free?", f"Yes. The data connector runs on Cloudflare's free plan with a daily cap shared by everyone, and the code is MIT-licensed. For heavy use, deploy your own copy in a few minutes: <a href=\"{GH}/blob/main/docs/SELF_HOSTING.md\">self-hosting guide</a>."],
        ["Where do the numbers come from?", "From the filings themselves: SEC EDGAR for US companies, ESEF reports on filings.xbrl.org for European ones, plus the U.S. Treasury, the ECB and Damodaran's datasets. Every figure carries its source."],
        ["Does the server see my workbook?", f"No. The review scripts run in your own Claude session. The server only sees the values the associate sends to verify_value, and keeps no user data. <a href=\"{GH}/blob/main/PRIVACY.md\">Privacy</a>."],
        ["What doesn't it do?", "No share prices and no consensus estimates: a market cap needs a price you provide. European coverage is partial and annual only. Banks and insurers are flagged, since a standard DCF doesn't fit them."],
        ["Does it replace a reviewer?", "No. It catches what can be checked: figures against filings, formulas against rules, language against a checklist. Everything is a draft until you sign it off."],
        ["Is it made by Anthropic?", "No. deskstack is an independent open-source project that works with Claude. It is not affiliated with or endorsed by Anthropic."],
    ],
    # final
    "end_t1": "Tie out your next model.", "end_t2": "Before anyone else does.",
    # footer
    "f_product": "Product", "f_docs": "Docs", "f_project": "Project",
    "f_links": {"tutorial": "Tutorial", "tools": "Data tools", "roles": "Roles", "data": "Data sources", "self": "Self-hosting", "bench": "Benchmark", "privacy": "Privacy", "security": "Security", "license": "MIT license"},
    "f_credit": "Data from SEC EDGAR, XBRL International's filings.xbrl.org, the U.S. Treasury, ECB statistics and Aswath Damodaran (NYU Stern). SEC XBRL handling builds on open-finance-mcp by Nathanael Johnson.",
    "f_disc": "Independent open-source project. Not affiliated with or endorsed by Anthropic. Data may be incomplete or delayed. Not investment advice.",
}

fr = {
    "lang": "fr", "other_lang": "en", "other_href": "../", "other_name": "English",
    "title": "deskstack : chaque chiffre rapproché du dépôt officiel",
    "desc": f"Des données financières gratuites et sourcées pour Claude, et une équipe de revue qui rapproche chaque chiffre de votre modèle du dépôt SEC ou ESEF. Open source.",
    "skip": "Aller à l'installation", "nav": "Principal",
    "n_how": "Fonctionnement", "n_bench": "Benchmark", "n_data": "Données", "n_faq": "FAQ", "n_install": "Installer",
    "h1a": "Chaque chiffre de votre modèle,", "h1b": "rapproché du dépôt officiel.",
    "lede_b": "Une équipe deal dans Claude.",
    "lede": "Un agent construit le modèle à partir de données gratuites et sourcées. D'autres rapprochent chaque chiffre du dépôt SEC ou européen. Rien ne sort sans votre accord.",
    "cta": "Installer dans Claude", "cta2": "Voir le benchmark",
    "c_associate": "Associate", "c_you": "Vous",
    "note": f"Déposé 391{T}035, pas 391{T}053{N}: deux chiffres inversés.",
    "cell_words": {"revenue": "CA", "ebit": "EBIT", "tax": "Impôt", "netdebt": "Dette nette", "awaiting": "en attente", "tieout": "Pointage"},
    "stats": [
        [f"0 sur 3{T}230", "chiffres faux avec les données deskstack, sur 199 DCF et tableaux de comparables"],
        [f"3,5{N}%", "de chiffres faux avec la recherche web seule (DCF), relus à la main contre les dépôts"],
        ["⅓", "du coût par modèle, et 2 à 5 fois plus rapide"],
        [f"10{T}419", "entreprises américaines, plus de grands émetteurs européens, directement depuis les dépôts"],
    ],
    "stats_note": "50 entreprises × DCF et comparables × 3 configurations, Claude Sonnet 5.5, novembre 2026. Le zéro tient en partie à la méthode : la notation vérifie contre les mêmes données, elles-mêmes comparées chaque nuit à deux autres parseurs.",
    "sc_t1": "Un agent construit le modèle.", "sc_t2": "D'autres vérifient chaque chiffre.",
    "sc_p": "Chaque rôle est un skill avec sa propre checklist et un rapport fixe. Les relecteurs signalent ; ils ne modifient jamais votre fichier.",
    "tabs": [
        ["analyst", "/analyst", "Construit le modèle", "Un DCF trois états ou un tableau de comparables à partir de données sourcées, après avoir validé les hypothèses avec vous."],
        ["associate", "/associate", "Rapproche du dépôt", "Chaque chiffre saisi vérifié contre le 10-K ou le rapport ESEF, cellule par cellule, avec la raison quand il ne concorde pas."],
        ["vp", "/vp-review", "Relit le modèle", "Contrôles déterministes : valeurs en dur, formules cassées, WACC contre croissance, conventions de signe, puis les hypothèses contre l'historique."],
        ["compliance", "/compliance", "Vérifie avant diffusion", "Avertissement, sources, saisies datées, aucun langage de conseil et aucune instruction cachée."],
        ["signoff", "/sign-off", "Vous attend", "Montre chaque point ouvert et n'exporte une copie signée qu'après votre accord, dans vos propres mots."],
    ],
    "m_title": "Apple · DCF · M USD",
    "m_src": "Source : Apple 10-K FY2025 · 0000320193-25-000079 · sec.gov",
    "m_inputs": "Hypothèses", "m_hist": "Historique, depuis les dépôts",
    "m_line": "Ligne", "m_model": "Modèle", "m_filed": "Déposé",
    "m_tie_sum": "13 chiffres sur 14 concordent avec le 10-K d'Apple. 1 écart.",
    "m_typo": f"Coquille : deux chiffres voisins semblent inversés (déposé 391{T}035, saisi 391{T}053).",
    "m_vp_sum": "Contrôle du modèle : propre", "m_vp_counts": "0 bloquant · 0 majeur · 0 mineur",
    "vp_checks": ["Valeurs en dur", "Cohérence des formules", "Valeurs d'erreur", "WACC contre croissance terminale", "Croissance terminale contre PIB", "Convention de signe", "Calendrier d'actualisation"],
    "m_c_sum": "Conformité : 10 conformes, 0 échec",
    "c_checks": ["Avertissement brouillon / pas un conseil en investissement", "Chaque chiffre saisi est sourcé", "Aucune source fictive ou « de mémoire »", "Les saisies de l'utilisateur sont datées", "Aucun langage de recommandation ou de promesse", "Aucune instruction adressée à une IA ou à un relecteur"],
    "m_s_rows": [["Rapprochement des dépôts", "OK", "14 concordent"], ["Revue du modèle", "OK", "0 bloquant, 0 majeur"], ["Conformité", "OK", "10 conformes, 0 échec"]],
    "m_s_token": "Jeton d'approbation", "m_s_wait": "Rien n'est exporté avant votre accord, dans vos propres mots.",
    "m_s_btn": "Approuver et exporter",
    "ln_t1": "Les agents construisent et vérifient.", "ln_t2": "Vous signez.",
    "ln_agents": "Agents", "ln_you": "Vous",
    "ln_steps": ["Hypothèses", "Construction", "Pointage", "Revue", "Contradiction", "Conformité", "Accord"],
    "ln_p": "Dans Claude Code et Cowork, les relecteurs tournent comme des agents séparés qui ne voient jamais comment le modèle a été construit. Ils relisent aussi votre travail : n'importe quel .xlsx.",
    "dk_t1": "Vérifié contre le dépôt.", "dk_t2": "Pas contre un autre modèle.",
    "dk_p": "verify_value lit le chiffre déposé pour la même entreprise, la même ligne et la même période, et dit pourquoi un chiffre diffère : échelle, signe, devise, période, ligne ou coquille.",
    "dk_steps": ["Lire le dépôt", "Écrire le modèle", "Rapprocher", "Corriger et revérifier"],
    "dk_card1_t": "Une raison, pas juste une cellule rouge",
    "dk_card1_p": "Chaque écart revient avec la valeur déposée, le numéro du dépôt et la cause probable.",
    "dk_hints": [["Échelle", "Saisi en milliers, déposé en millions"], ["Signe", "Investissements saisis en négatif"], ["Période", "Correspond à l'exercice 2026, pas aux douze derniers mois"], ["Coquille", "Deux chiffres voisins inversés"]],
    "dk_card2_t": "Le voir repérer une coquille",
    "dk_card2_p": "Les scripts de revue sur le DCF FY2025 d'Apple, avec une coquille glissée. La revue du modèle ne la voit pas ; le rapprochement avec le 10-K, si.",
    "demo_alt": f"Enregistrement de terminal : /associate trouve 13 chiffres sur 14 conformes au 10-K d'Apple et signale le CA FY2024 391{T}053 contre 391{T}035 déposé, deux chiffres inversés ; /vp-review trouve le modèle propre ; après correction, /sign-off montre tous les contrôles au vert et attend l'accord.",
    "b_t1": "Nous l'avons mesuré.", "b_t2": "Puis relu chaque chiffre faux à la main.",
    "b_p": "Claude Sonnet 5.5 a construit un DCF et un tableau de comparables pour chacune de 50 entreprises (35 américaines, 15 européennes), de trois façons. Chaque chiffre publié a été noté contre le dépôt.",
    "b_h_arm": "Configuration", "b_h_wrong": "Chiffres publiés faux", "b_h_cost": "Coût / modèle", "b_h_time": "Temps",
    "b_link": "Analyse et transcriptions",
    "benches": [
        {"t": "DCF, 50 sociétés", "analysis": DCF, "rows": [
            ["Recherche web seule", f"3,5{N}%", "20 sur 573", f"0,23{N}$", "58 s", "3.5"],
            ["Données deskstack", f"0{N}%", "0 sur 593", f"0,07{N}$", "18 s", ""],
            ["deskstack + relecteurs", f"0{N}%", "0 sur 606", f"0,10{N}$", "32 s", ""]]},
        {"t": "Comparables, les mêmes 50 sociétés", "analysis": COMPS, "rows": [
            ["Recherche web seule", f"3,6{N}%", "16 sur 445, et 7 laissés à 0", f"0,56{N}$", "171 s", "3.6"],
            ["Données deskstack", f"0{N}%", f"0 sur 1{T}021", f"0,17{N}$", "36 s", ""],
            ["deskstack + relecteurs", f"0{N}%", f"0 sur 1{T}010", f"0,22{N}$", "51 s", ""]]},
    ],
    "b_cards": [
        ["Ce que la recherche web a raté", "Dans les DCF, des chiffres introuvables remplis quand même : nombres d'actions calculés, investissements estimés, chiffre d'affaires non comptable. Dans les comparables, des chiffres sur douze mois en retard d'un trimestre, pris chez un agrégateur."],
        ["Avec plus de recherches ?", "Une reprise préenregistrée avec 30 recherches et un effort élevé a encore écrit un chiffre qui n'est pas celui du dépôt. Les valeurs fictives ont disparu ; le coût par tableau a plus que doublé."],
        ["Il nous vérifie aussi", "Les runs ont trouvé des lacunes dans les données de deskstack et deux bugs dans la notation. Tous corrigés, testés et documentés avec les résultats."],
    ],
    "b_robust": "Test de robustesse",
    "d_t1": "Des données gratuites,", "d_t2": "avec la source sur chaque chiffre.",
    "d_p": "Uniquement des dépôts officiels et des jeux de données publics. Un chiffre non déposé reste vide ; il n'est jamais estimé.",
    "data": [
        ["SEC EDGAR", "États financiers, États-Unis", "Dépôts 10-K, 10-Q et 20-F : annuels et douze derniers mois, pour les sociétés cotées aux États-Unis, y compris les émetteurs étrangers en IFRS."],
        ["filings.xbrl.org", "États financiers, Europe", "Rapports annuels ESEF d'une trentaine de grands émetteurs en France, aux Pays-Bas, en Espagne, en Finlande, en Italie et en Belgique."],
        ["Trésor américain · BCE", "Taux sans risque", "Rendements quotidiens de 1 mois à 30 ans."],
        ["Banque centrale européenne", "Taux de change", "Plus de 30 devises, à une date ou en moyenne sur une période."],
        ["Aswath Damodaran, NYU Stern", "Paramètres de valorisation", "Prime de risque par pays ; bêtas et coût du capital par secteur."],
        ["Chaque réponse", "Une citation", "Source, URL, numéro de dépôt, période et date sur chaque chiffre, pour ouvrir le dépôt d'où il vient."],
    ],
    "acc_t": "Exactitude, vérifiée chaque nuit",
    "acc_p": "Des questions de référence répondues exactement comme déposé, contre le connecteur en ligne, et chaque réponse relue depuis le dépôt par un parseur indépendant.",
    "acc_link": "Comment c'est vérifié",
    "i_t1": "Installer en trois étapes.", "i_t2": "Sans terminal, sans compte à créer.",
    "i_p": "Il vous faut un compte Claude avec l'exécution de code activée ; les rôles demandent un forfait payant.",
    "s1": "Ajouter le connecteur de données", "s1p": "Dans Claude, ouvrez Réglages, puis Connecteurs, puis Ajouter un connecteur personnalisé. Collez l'URL, sans connexion.",
    "s2": "Ajouter l'équipe deal", "s2p": "Ouvrez Personnaliser, puis Plugins, puis Ajouter une marketplace. Collez ce dépôt, puis installez deskstack.",
    "s3": "Demander un modèle", "s3p": "Claude construit le DCF, fait vérifier et relire chaque chiffre, puis attend votre accord.",
    "placeholder": "Bientôt disponible", "copy": "Copier", "copied": "Copié", "selected": "Sélectionné : faites Ctrl+C",
    "pending": f'Le connecteur hébergé n\'est pas encore en ligne. Vous pouvez lancer votre propre copie gratuitement en quelques minutes : <a href="{GH}/blob/main/docs/SELF_HOSTING.md">guide d\'auto-hébergement</a>.',
    "tut": "Lire le tutoriel",
    "q_t1": "Vos questions,", "q_t2": "nos réponses.",
    "faq": [
        ["Est-ce gratuit ?", f"Oui. Le connecteur tourne sur l'offre gratuite de Cloudflare avec un plafond quotidien partagé, et le code est sous licence MIT. Pour un usage intensif, déployez votre propre copie en quelques minutes : <a href=\"{GH}/blob/main/docs/SELF_HOSTING.md\">guide d'auto-hébergement</a>."],
        ["D'où viennent les chiffres ?", "Des dépôts eux-mêmes : SEC EDGAR pour les sociétés américaines, les rapports ESEF sur filings.xbrl.org pour les européennes, plus le Trésor américain, la BCE et les données de Damodaran. Chaque chiffre porte sa source."],
        ["Le serveur voit-il mon classeur ?", f"Non. Les scripts de revue tournent dans votre propre session Claude. Le serveur ne voit que les valeurs que l'associate envoie à verify_value, et ne conserve aucune donnée utilisateur. <a href=\"{GH}/blob/main/PRIVACY.md\">Confidentialité</a>."],
        ["Que ne fait-il pas ?", "Pas de cours de bourse ni de consensus : une capitalisation demande un cours que vous fournissez. La couverture européenne est partielle et annuelle uniquement. Les banques et assureurs sont signalés, un DCF standard ne leur convient pas."],
        ["Remplace-t-il un relecteur ?", "Non. Il attrape ce qui se vérifie : les chiffres contre les dépôts, les formules contre des règles, le langage contre une checklist. Tout reste un brouillon jusqu'à votre accord."],
        ["Est-ce fait par Anthropic ?", "Non. deskstack est un projet open source indépendant qui fonctionne avec Claude. Il n'est ni affilié à Anthropic ni approuvé par elle."],
    ],
    "end_t1": "Rapprochez votre prochain modèle.", "end_t2": "Avant que quelqu'un d'autre ne le fasse.",
    "f_product": "Produit", "f_docs": "Docs", "f_project": "Projet",
    "f_links": {"tutorial": "Tutoriel", "tools": "Outils de données", "roles": "Rôles", "data": "Sources de données", "self": "Auto-hébergement", "bench": "Benchmark", "privacy": "Confidentialité", "security": "Sécurité", "license": "Licence MIT"},
    "f_credit": "Données de SEC EDGAR, filings.xbrl.org (XBRL International), du Trésor américain, de la BCE et d'Aswath Damodaran (NYU Stern). Le traitement XBRL de la SEC s'appuie sur open-finance-mcp de Nathanael Johnson.",
    "f_disc": "Projet open source indépendant. Ni affilié à Anthropic ni approuvé par elle. Les données peuvent être incomplètes ou en retard. Pas un conseil en investissement.",
}


def frtype(s):
    """Non-breaking spaces before French double punctuation (strings that already contain HTML are left alone)."""
    if not isinstance(s, str) or "<a " in s:
        return s
    for p in [" :", " ;", " ?", " !"]:
        s = s.replace(p, N + p[1:])
    return s


def walk(x):
    if isinstance(x, str):
        return frtype(x)
    if isinstance(x, list):
        return [walk(v) for v in x]
    if isinstance(x, dict):
        return {k: (v if k in ("analysis", "lang", "other_lang", "other_href") else walk(v)) for k, v in x.items()}
    return x


def fr_links(s):
    # HTML strings: fix spacing only outside tags.
    return s.replace(" : <a", N + ": <a").replace(" ? ", N + "? ") if isinstance(s, str) else s


fr = walk(fr)
fr["faq"] = [[q, fr_links(a)] for q, a in fr["faq"]]
fr["pending"] = fr_links(fr["pending"])

if __name__ == "__main__":
    assert set(en) == set(fr), sorted(set(en) ^ set(fr))
    Path(__file__).with_name("content.json").write_text(json.dumps({"en": en, "fr": fr}, ensure_ascii=False, indent=2))
    print("Wrote site/src/content.json")
