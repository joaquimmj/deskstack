# Glossary / Glossaire

Each entry: English, then French. Keep answers short and tie them to the user's numbers.

**DCF (discounted cash flow)**
- EN: Value today of the cash a business will generate, discounted at the cost of capital. Free cash flow for each
  forecast year + a terminal value for the years after.
- FR: Valeur aujourd'hui des flux de trésorerie futurs, actualisés au coût du capital. Flux de chaque année de
  prévision + une valeur terminale pour la suite.

**Unlevered free cash flow**
- EN: NOPAT + D&A − capex (− increase in working capital): cash available to all investors before debt payments.
- FR: NOPAT + amortissements − investissements (− hausse du BFR) : trésorerie disponible pour tous les financeurs,
  avant service de la dette.

**WACC (weighted average cost of capital)**
- EN: The return investors require, blending equity and debt: E/(D+E) × cost of equity + D/(D+E) × cost of debt ×
  (1 − tax). Cost of equity ≈ risk-free rate + beta × equity risk premium.
- FR : Coût moyen pondéré du capital : rendement exigé par actionnaires et prêteurs, pondéré par leur poids. Coût des
  fonds propres ≈ taux sans risque + bêta × prime de risque.

**Terminal value**
- EN: Value of all cash flows after the forecast. Gordon growth: last FCF × (1 + g) / (WACC − g). If it is more than
  ~75% of enterprise value, the answer depends mostly on g and WACC.
- FR : Valeur des flux au-delà de la prévision. Formule de Gordon : dernier flux × (1 + g) / (WACC − g). Au-delà
  d'environ 75 % de la valeur d'entreprise, le résultat dépend surtout de g et du WACC.

**Terminal growth (g)**
- EN: Perpetual growth after the forecast. Should stay at or below long-run nominal GDP growth (~2–4%) and well
  below WACC.
- FR : Croissance à l'infini après la prévision. À garder sous la croissance nominale de long terme du PIB
  (~2–4 %) et bien sous le WACC.

**Mid-year convention**
- EN: Cash arrives through the year, so each year is discounted by n − 0.5 periods instead of n.
- FR : Convention de milieu d'année : les flux arrivent au fil de l'année, on actualise sur n − 0,5 périodes au
  lieu de n.

**Enterprise value (EV) / Equity value**
- EN: EV = value of operations. Equity value = EV − net debt. Per share = equity value / diluted shares.
- FR : Valeur d'entreprise = valeur de l'exploitation. Valeur des fonds propres = VE − dette nette. Par action =
  fonds propres / actions diluées.

**Net debt**
- EN: Total debt − cash − short-term investments (deskstack's definition). Say whether leases are included.
- FR : Dette financière − trésorerie − placements court terme (définition deskstack). Préciser si les loyers
  (IFRS 16) sont inclus.

**Multiples (EV/Revenue, EV/EBITDA, P/E)**
- EN: Price of comparable companies relative to a metric. EV multiples use enterprise value; P/E uses market cap.
  "n.m." means not meaningful (negative or zero denominator).
- FR : Prix des sociétés comparables rapporté à un agrégat. Les multiples de VE utilisent la valeur d'entreprise ;
  le PER utilise la capitalisation. « n.m. » = non significatif (dénominateur négatif ou nul).

**Tie-out**
- EN: Checking each hardcoded number against its source document (here, the filing via `verify_value`).
- FR : Rapprochement : vérifier chaque chiffre saisi contre son document source (ici le dépôt officiel, via
  `verify_value`).

**LTM (last twelve months)**
- EN: The latest four quarters: last fiscal year + year-to-date − prior year-to-date.
- FR : Douze derniers mois : dernier exercice + cumul de l'année en cours − cumul de l'an passé à la même date.

**Fiscal year (FY)**
- EN: A company's reporting year. Apple's FY2025 ended 2025-09-27; always state the end date when it isn't December.
- FR : Exercice comptable. L'exercice 2025 d'Apple s'est terminé le 27/09/2025 ; préciser la date quand ce n'est pas
  décembre.
