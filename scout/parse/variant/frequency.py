
def parse_frequencies(variant, transcripts):
    """Add the frequencies to a variant
    
    Frequencies are parsed either directly from keys in info fieds or from the 
    transcripts is they are annotated there.

    Args:
        variant(cyvcf2.Variant): A parsed vcf variant
        transcripts(iterable(dict)): Parsed transcripts

    Returns:
        frequencies(dict): A dictionary with the relevant frequencies
    """
    frequencies = {}
    # These lists could be extended...
    thousand_genomes_keys = ['1000GAF']
    thousand_genomes_max_keys = ['1000G_MAX_AF']

    exac_keys = ['EXACAF']
    exac_max_keys = ['ExAC_MAX_AF', 'EXAC_MAX_AF']

    gnomad_keys = ['GNOMADAF', 'GNOMAD_AF']
    gnomad_max_keys = ['GNOMADAF_POPMAX', 'GNOMADAF_MAX']
    
    for test_key in thousand_genomes_keys:
        thousand_g = parse_frequency(variant, test_key)
        if thousand_g:
            frequencies['thousand_g'] = thousand_g
            break

    for test_key in thousand_genomes_max_keys:
        thousand_g_max = parse_frequency(variant, test_key)
        if thousand_g_max:
            frequencies['thousand_g_max'] = thousand_g_max
            break

    for test_key in exac_keys:
        exac = parse_frequency(variant, test_key)
        if exac:
            frequencies['exac'] = exac
            break

    for test_key in exac_max_keys:
        exac_max = parse_frequency(variant, test_key)
        if exac_max:
            frequencies['exac_max'] = exac_max
            break

    for test_key in gnomad_keys:
        gnomad = parse_frequency(variant, test_key)
        if gnomad:
            frequencies['gnomad'] = gnomad
            break

    for test_key in gnomad_max_keys:
        gnomad_max = parse_frequency(variant, test_key)
        if gnomad_max:
            frequencies['gnomad_max'] = gnomad_max
            break

    # Search transcripts if not found in VCF
    if not frequencies:
        for transcript in transcripts:
            exac = transcript.get('exac_maf')
            exac_max = transcript.get('exac_max')
            
            thousand_g = transcript.get('thousand_g_maf')
            thousandg_max = transcript.get('thousandg_max')
            
            gnomad = transcript.get('gnomad_maf')
            gnomad_max = transcript.get('gnomad_max')
            if exac:
                frequencies['exac'] = exac
            if exac_max:
                frequencies['exac_max'] = exac_max
            if thousand_g:
                frequencies['thousand_g'] = thousand_g
            if thousandg_max:
                frequencies['thousand_g_max'] = thousandg_max
            if gnomad:
                frequencies['gnomad'] = gnomad
            if gnomad_max:
                frequencies['gnomad_max'] = gnomad_max

    #These are SV-specific frequencies
    thousand_g_left = parse_frequency(variant, 'left_1000GAF')
    if thousand_g_left:
        frequencies['thousand_g_left'] = thousand_g_left 
    
    thousand_g_right = parse_frequency(variant, 'right_1000GAF')
    if thousand_g_right:
        frequencies['thousand_g_right'] = thousand_g_right 

    return frequencies


def parse_frequency(variant, info_key):
    """Parse any frequency from the info dict
    
    Args:
        variant(cyvcf2.Variant)
        info_key(str)
    
    Returns:
        frequency(float): or None if frequency does not exist
    """
    raw_annotation = variant.INFO.get(info_key)
    raw_annotation = None if raw_annotation == '.' else raw_annotation
    frequency = float(raw_annotation) if raw_annotation else None
    return frequency

def parse_sv_frequencies(variant):
    """Parsing of some custom sv frequencies
    
    These are very specific at the moment, this will hopefully get better over time when the 
    field of structural variants is more developed.
    
    Args:
        variant(cyvcf2.Variant)
    
    Returns:
        sv_frequencies(dict)
    """
    frequency_keys = [
        'clingen_cgh_benignAF', 
        'clingen_cgh_benign',
        'clingen_cgh_pathogenicAF',
        'clingen_cgh_pathogenic',
        'clingen_ngi',
        'clingen_ngiAF',
        'decipherAF',
        'decipher'
    ]
    sv_frequencies = {}
    
    for key in frequency_keys:
        value = variant.INFO.get(key, 0)
        if 'AF' in key:
            value = float(value)
        else:
            value = int(value)
        if value > 0:
            sv_frequencies[key] = value
    
    return sv_frequencies
    