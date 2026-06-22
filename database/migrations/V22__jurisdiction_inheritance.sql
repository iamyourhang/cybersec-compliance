-- V22__jurisdiction_inheritance.sql
-- Market-level inheritance. EU regulations stay stored under EU, while EU member
-- markets can display/query them as inherited applicable requirements.

CREATE TABLE IF NOT EXISTS jurisdiction_inheritance (
    parent_code         VARCHAR(10) NOT NULL REFERENCES countries(code) ON UPDATE CASCADE,
    child_code          VARCHAR(10) NOT NULL REFERENCES countries(code) ON UPDATE CASCADE,
    relation_type       VARCHAR(40) NOT NULL DEFAULT 'member_state',
    reason              TEXT NOT NULL,
    effective_from      DATE,
    effective_to        DATE,
    enabled             BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (parent_code, child_code, relation_type)
);

CREATE INDEX IF NOT EXISTS idx_jurisdiction_inheritance_child
    ON jurisdiction_inheritance(child_code, enabled);

INSERT INTO jurisdiction_inheritance (
    parent_code,
    child_code,
    relation_type,
    reason,
    effective_from,
    enabled
)
VALUES
    ('EU', 'AT', 'member_state', 'Austria is an EU Member State; EU-level cybersecurity product regulations apply to the Austrian market.', '1995-01-01', TRUE),
    ('EU', 'BE', 'member_state', 'Belgium is an EU Member State; EU-level cybersecurity product regulations apply to the Belgian market.', '1958-01-01', TRUE),
    ('EU', 'BG', 'member_state', 'Bulgaria is an EU Member State; EU-level cybersecurity product regulations apply to the Bulgarian market.', '2007-01-01', TRUE),
    ('EU', 'HR', 'member_state', 'Croatia is an EU Member State; EU-level cybersecurity product regulations apply to the Croatian market.', '2013-07-01', TRUE),
    ('EU', 'CY', 'member_state', 'Cyprus is an EU Member State; EU-level cybersecurity product regulations apply to the Cypriot market.', '2004-05-01', TRUE),
    ('EU', 'CZ', 'member_state', 'Czechia is an EU Member State; EU-level cybersecurity product regulations apply to the Czech market.', '2004-05-01', TRUE),
    ('EU', 'DK', 'member_state', 'Denmark is an EU Member State; EU-level cybersecurity product regulations apply to the Danish market.', '1973-01-01', TRUE),
    ('EU', 'EE', 'member_state', 'Estonia is an EU Member State; EU-level cybersecurity product regulations apply to the Estonian market.', '2004-05-01', TRUE),
    ('EU', 'FI', 'member_state', 'Finland is an EU Member State; EU-level cybersecurity product regulations apply to the Finnish market.', '1995-01-01', TRUE),
    ('EU', 'FR', 'member_state', 'France is an EU Member State; EU-level cybersecurity product regulations apply to the French market.', '1958-01-01', TRUE),
    ('EU', 'DE', 'member_state', 'Germany is an EU Member State; EU-level cybersecurity product regulations apply to the German market.', '1958-01-01', TRUE),
    ('EU', 'GR', 'member_state', 'Greece is an EU Member State; EU-level cybersecurity product regulations apply to the Greek market.', '1981-01-01', TRUE),
    ('EU', 'HU', 'member_state', 'Hungary is an EU Member State; EU-level cybersecurity product regulations apply to the Hungarian market.', '2004-05-01', TRUE),
    ('EU', 'IE', 'member_state', 'Ireland is an EU Member State; EU-level cybersecurity product regulations apply to the Irish market.', '1973-01-01', TRUE),
    ('EU', 'IT', 'member_state', 'Italy is an EU Member State; EU-level cybersecurity product regulations apply to the Italian market.', '1958-01-01', TRUE),
    ('EU', 'LV', 'member_state', 'Latvia is an EU Member State; EU-level cybersecurity product regulations apply to the Latvian market.', '2004-05-01', TRUE),
    ('EU', 'LT', 'member_state', 'Lithuania is an EU Member State; EU-level cybersecurity product regulations apply to the Lithuanian market.', '2004-05-01', TRUE),
    ('EU', 'LU', 'member_state', 'Luxembourg is an EU Member State; EU-level cybersecurity product regulations apply to the Luxembourg market.', '1958-01-01', TRUE),
    ('EU', 'MT', 'member_state', 'Malta is an EU Member State; EU-level cybersecurity product regulations apply to the Maltese market.', '2004-05-01', TRUE),
    ('EU', 'NL', 'member_state', 'Netherlands is an EU Member State; EU-level cybersecurity product regulations apply to the Dutch market.', '1958-01-01', TRUE),
    ('EU', 'PL', 'member_state', 'Poland is an EU Member State; EU-level cybersecurity product regulations apply to the Polish market.', '2004-05-01', TRUE),
    ('EU', 'PT', 'member_state', 'Portugal is an EU Member State; EU-level cybersecurity product regulations apply to the Portuguese market.', '1986-01-01', TRUE),
    ('EU', 'RO', 'member_state', 'Romania is an EU Member State; EU-level cybersecurity product regulations apply to the Romanian market.', '2007-01-01', TRUE),
    ('EU', 'SK', 'member_state', 'Slovakia is an EU Member State; EU-level cybersecurity product regulations apply to the Slovak market.', '2004-05-01', TRUE),
    ('EU', 'SI', 'member_state', 'Slovenia is an EU Member State; EU-level cybersecurity product regulations apply to the Slovenian market.', '2004-05-01', TRUE),
    ('EU', 'ES', 'member_state', 'Spain is an EU Member State; EU-level cybersecurity product regulations apply to the Spanish market.', '1986-01-01', TRUE),
    ('EU', 'SE', 'member_state', 'Sweden is an EU Member State; EU-level cybersecurity product regulations apply to the Swedish market.', '1995-01-01', TRUE)
ON CONFLICT (parent_code, child_code, relation_type) DO UPDATE SET
    reason = EXCLUDED.reason,
    effective_from = EXCLUDED.effective_from,
    effective_to = EXCLUDED.effective_to,
    enabled = EXCLUDED.enabled,
    updated_at = NOW();
