# clinvar Variant sheet
CLIVAR_HEADER = [
    '##Local ID',
    'Linking ID',
    'Gene symbol',
    'Reference sequence',
    'HGVS',
    'Chromosome',
    'Start',
    'Stop',
    'Reference allele',
    'Alternate allele',
    'Variation identifiers',
    'Condition ID type',
    'Condition ID value',
    'Condition comment',
    'Clinical significance',
    'Date last evaluated',
    'Assertion method',
    'Assertion method citation',
    'Mode of inheritance',
    'Clinical significance citations',
    'Citations or URLs for clinical significance without database identifiers',
    'Comment on clinical significance',
    'Drug response condition',
    'Functional consequence',
    'Comment on functional consequence'
]

# clinvar Variant sheet, optional fields
CLINVAR_OPTIONAL = {
    'Reference sequence' : False,
    'HGVS' : False,
    'Variation identifiers' : False,
    'Condition comment' : False,
    'Assertion method' : False,
    'Assertion method citation' : False,
    'Clinical significance citations' : False,
    'Citations or URLs for clinical significance without database identifiers' : False,
    'Comment on clinical significance' : False,
    'Drug response condition' : False,
    'Functional consequence' : False,
    'Comment on functional consequence' : False,
}

# clinvar CaseData sheet
CASEDATA_HEADER = [
    'Linking ID',
    'Individual ID',
    'Collection method',
    'Allele origin',
    'Affected status',
    'Structural variant method/analysis type',
    'Clinical features',
    'Comment on clinical features',
    'Date phenotype was evaluated',
    'Tissue',
    'Sex',
    'Age',
    'Population Group/Ethnicity',
    'Family history',
    'Proband',
    'Family ID',
    'Secondary finding',
    'Mosaicism',
    'Zygosity',
    'Co-occurrences, same gene',
    'Co-occurrences, other genes',
    'Evidence citations',
    'Citations or URLs that cannot be represented in evidence citations column',
    'Comment on evidence',
    'Platform type',
    'Platform name',
    'Method',
    'Method purpose',
    'Method citations',
    'Software name and version',
    'Testing laboratory',
    'Date variant was reported to submitter'
]

# clinvar CaseData sheet, optional fields for clinvar but some are pre-determined for clinvar scout form.
CASEDATA_OPTIONAL = {
    'Structural variant method/analysis type' : False,
    'Collection method' : 'clinical testing',
    'Comment on clinical features' : False,
    'Date phenotype was evaluated' : False,
    'Tissue' : False,
    'Age' : False,
    'Population Group/Ethnicity' : False,
    'Family ID' : False,
    'Co-occurrences, same gene' : False,
    'Co-occurrences, other genes' : False,
    'Evidence citations' : False,
    'Citations or URLs that cannot be represented in evidence citations column' : False,
    'Comment on evidence' : False,
    'Platform type' : 'next-gen sequencing',
    'Method' : False,
    'Method purpose' : False,
    'Method citations' : False,
    'Software name and version' : False,
    'Testing laboratory' : 'Clinical Genomics - SciLifeLab Solna, Sweden.',
}
