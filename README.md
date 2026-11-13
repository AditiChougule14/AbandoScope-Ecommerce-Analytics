# AbandoScope

## E-Commerce Customer Behaviour & Cart Abandonment Analytics

AbandoScope is an e-commerce analytics project that explores customer
browsing, cart activity and purchase behaviour using event-level and
session-level data. It combines Python-based data preparation, SQL
analysis and interactive Power BI dashboards to help understand product
performance and cart abandonment patterns.

## Project objectives

-   Understand the distribution of view, cart and purchase events.
-   Analyse customer sessions that contain cart activity but no
    purchase.
-   Examine product, brand and category performance.
-   Estimate the value associated with potentially abandoned carts.
-   Present key findings through interactive Power BI dashboards.

## Dataset

This project uses the **REES46 E-Commerce Behavior Data from a
Multi-Category Store (October 2019)** dataset.

The raw dataset is large and is not included in this repository.
Download the October 2019 source dataset from Kaggle and place it in
`data/raw/` using the filename expected by the project scripts.

Dataset source:
https://www.kaggle.com/datasets/mkechinov/ecommerce-behavior-data-from-multi-category-store

## Technology stack

-   Python and Pandas --- data cleaning, preparation and analysis
-   SQL --- database scripts and analytical queries
-   Power BI Desktop --- interactive dashboards
-   Google Antigravity --- project development environment

## Project workflow

1.  **Data preparation:** the raw October 2019 event data is cleaned and
    prepared for analysis.
2.  **Exploratory analysis:** event distribution, category performance,
    brand performance and product performance are examined.
3.  **Session analysis:** sessions are assessed for cart activity and
    purchase activity.
4.  **KPI generation and validation:** summary metrics and validation
    outputs are generated.
5.  **Dashboarding:** prepared CSV summaries are used in Power BI.

## Cart abandonment definition and interpretation

For this project, an **abandoned session** is a session with at least
one cart event and no purchase event.

The cart abandonment rate is calculated as:

`Abandoned Sessions / Sessions with Cart Activity`

This is a session-level definition based on the available event data.
The source data does not contain an explicit checkout event, so this
project does not measure checkout abandonment.

**Potential Abandoned Cart Value** is an estimate based on cart-event
values in sessions classified as abandoned. It should not be interpreted
as confirmed lost revenue; repeated cart events may affect the estimate.

The cart-to-purchase conversion figure shown in the dashboard is an
event-count ratio (purchase events divided by cart events), not a
unique-session conversion rate.

## Power BI dashboards

The Power BI report contains three pages:

1.  **E-Commerce Overview** --- overall event activity, revenue,
    category performance and leading products and brands.
2.  **Cart Abandonment Analysis** --- cart-session outcomes, abandonment
    KPIs, category comparisons and the event funnel.
3.  **Customer Behaviour & Product Insights** --- leading products by
    views, cart events and purchases, plus brand and category insights.

Open `AbandoScope_Dashboard.pbix` in Power BI Desktop to explore the
report.

## Repository structure

``` text
AbandoScope_Analytics/
├── data/
│   ├── raw/                 # Downloaded source data (not committed)
│   └── processed/
│       └── powerbi/         # Prepared CSV summaries for Power BI
├── docs/
│   ├── cleaning_report.md
│   ├── data_dictionary.md
│   ├── session_audit.tsv
│   └── validation_report.md
├── reports/
│   └── eda/                 # EDA report and generated charts
├── scripts/                 # Python data preparation and validation scripts
├── sql/                     # SQL setup, validation and analysis queries
├── tmp/                     # Temporary working files
└── AbandoScope_Dashboard.pbix
```

## Running the project

1.  Install Python and the required packages used by the project
    scripts.
2.  Download the October 2019 dataset from the source linked above.
3.  Place the source file in `data/raw/` and ensure its filename matches
    the input expected by the scripts.
4.  Review the scripts in `scripts/` and run the data-cleaning and
    analysis workflow in the required order.
5.  Use the generated CSV summaries in `data/processed/powerbi/` with
    Power BI Desktop.
6.  Open `AbandoScope_Dashboard.pbix`.

The exact package list and script execution order should be documented
from the project's actual environment before publishing setup
instructions. Do not assume a `requirements.txt` file exists unless one
has been added and verified.

## Documentation

Additional project documentation is available in `docs/`, including the
data dictionary, cleaning report, session audit and validation report.
Exploratory analysis outputs are available in `reports/eda/`.

## Notes before publishing

-   Do not commit the multi-gigabyte raw or cleaned CSV datasets.
-   Do not commit temporary files, Python cache folders (`__pycache__/`,
    `*.pyc`) or local environment files.
-   Include the prepared Power BI CSV summaries if their size and
    licensing permit.
-   Add screenshots of all three dashboard pages to the repository and
    link them here once they are saved.
-   Verify the source dataset's licence and attribution requirements
    before redistributing any data.

## Author

Developed as an academic analytics project using Google Antigravity,
Python, SQL and Power BI.
