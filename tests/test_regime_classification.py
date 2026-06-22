from database.repository import (
    GENERAL_CYBER_LAW_CATEGORY,
    PRODUCT_REGIME_CATEGORY,
    classify_regime_category,
)


def test_cyber_resilience_act_is_product_regime():
    category = classify_regime_category(
        {
            "name": "Regulation (EU) 2024/2847 on horizontal cybersecurity requirements for products with digital elements (Cyber Resilience Act)",
            "entry_type": "regulation",
            "summary": "Mandatory cybersecurity requirements for products with digital elements placed on the EU market.",
        }
    )

    assert category == PRODUCT_REGIME_CATEGORY


def test_general_cybercrime_law_is_not_product_regime():
    category = classify_regime_category(
        {
            "name": "Cybercrime Act",
            "entry_type": "regulation",
            "summary": "General offences and criminal procedure for computer misuse.",
        }
    )

    assert category == GENERAL_CYBER_LAW_CATEGORY
