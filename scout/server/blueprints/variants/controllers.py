# -*- coding: utf-8 -*-
import logging
import os.path

from pprint import pprint as pp

from datetime import date
from flask import url_for, flash
from flask_mail import Message

from scout.constants import (CLINSIG_MAP, ACMG_MAP, MANUAL_RANK_OPTIONS,
                             ACMG_OPTIONS, DISMISS_VARIANT_OPTIONS,
                             ACMG_COMPLETE_MAP, CALLERS, SPIDEX_HUMAN)
from scout.constants.acmg import ACMG_CRITERIA
from scout.constants.variants_export import EXPORT_HEADER
from scout.models.event import VERBS_MAP
from scout.server.utils import institute_and_case
from scout.server.links import (add_gene_links, ensembl, add_tx_links)
from .forms import CancerFiltersForm
from scout.server.blueprints.genes.controllers import gene

LOG = logging.getLogger(__name__)


class MissingSangerRecipientError(Exception):
    pass


def variants(store, institute_obj, case_obj, variants_query, page=1, per_page=50):
    """Pre-process list of variants."""
    variant_count = variants_query.count()
    skip_count = per_page * max(page - 1, 0)
    more_variants = True if variant_count > (skip_count + per_page) else False

    return {
        'variants': (parse_variant(store, institute_obj, case_obj, variant_obj, update=True) for
                     variant_obj in variants_query.skip(skip_count).limit(per_page)),
        'more_variants': more_variants,
    }


def sv_variants(store, institute_obj, case_obj, variants_query, page=1, per_page=50):
    """Pre-process list of SV variants."""
    skip_count = (per_page * max(page - 1, 0))
    more_variants = True if variants_query.count() > (skip_count + per_page) else False

    return {
        'variants': (parse_variant(store, institute_obj, case_obj, variant) for variant in
                     variants_query.skip(skip_count).limit(per_page)),
        'more_variants': more_variants,
    }

def str_variants(store, institute_obj, case_obj, variants_query, page=1, per_page=50):
    """Pre-process list of STR variants."""
    # Nothing unique to STRs on this level. Inheritance?
    return variants(store, institute_obj, case_obj, variants_query, page, per_page)

def str_variant(store, institute_id, case_name, variant_id):
    """Pre-process an STR variant entry for detail page.

    Adds information to display variant

    Args:
        store(scout.adapter.MongoAdapter)
        institute_id(str)
        case_name(str)
        variant_id(str)

    Returns:
        detailed_information(dict): {
            'institute': <institute_obj>,
            'case': <case_obj>,
            'variant': <variant_obj>,
            'overlapping_snvs': <overlapping_snvs>,
            'manual_rank_options': MANUAL_RANK_OPTIONS,
            'dismiss_variant_options': DISMISS_VARIANT_OPTIONS
        }
        """

    institute_obj, case_obj = institute_and_case(store, institute_id, case_name)
    variant_obj =  store.variant(variant_id)

    # fill in information for pilup view
    variant_case(store, case_obj, variant_obj)

    variant_obj['callers'] = callers(variant_obj, category='str')

    # variant_obj['str_ru']
    # variant_obj['str_repid']
    # variant_obj['str_ref']

    variant_obj['comments'] = store.events(institute_obj, case=case_obj,
                                           variant_id=variant_obj['variant_id'], comments=True)

    return {
        'institute': institute_obj,
        'case': case_obj,
        'variant': variant_obj,
        'overlapping_snvs': overlapping_snvs,
        'manual_rank_options': MANUAL_RANK_OPTIONS,
        'dismiss_variant_options': DISMISS_VARIANT_OPTIONS
    }

def sv_variant(store, institute_id, case_name, variant_id):
    """Pre-process an SV variant entry for detail page.

    Adds information to display variant

    Args:
        store(scout.adapter.MongoAdapter)
        institute_id(str)
        case_name(str)
        variant_id(str)

    Returns:
        detailed_information(dict): {
            'institute': <institute_obj>,
            'case': <case_obj>,
            'variant': <variant_obj>,
            'overlapping_snvs': <overlapping_snvs>,
            'manual_rank_options': MANUAL_RANK_OPTIONS,
            'dismiss_variant_options': DISMISS_VARIANT_OPTIONS
        }
    """
    institute_obj, case_obj = institute_and_case(store, institute_id, case_name)
    variant_obj =  store.variant(variant_id)

    # fill in information for pilup view
    variant_case(store, case_obj, variant_obj)

    # frequencies
    variant_obj['frequencies'] = [
        ('1000G', variant_obj.get('thousand_genomes_frequency')),
        ('1000G (left)', variant_obj.get('thousand_genomes_frequency_left')),
        ('1000G (right)', variant_obj.get('thousand_genomes_frequency_right')),
        ('ClinGen CGH (benign)', variant_obj.get('clingen_cgh_benign')),
        ('ClinGen CGH (pathogenic)', variant_obj.get('clingen_cgh_pathogenic')),
        ('ClinGen NGI', variant_obj.get('clingen_ngi')),
        ('Decipher', variant_obj.get('decipher')),
    ]

    variant_obj['callers'] = callers(variant_obj, category='sv')
    overlapping_snvs = (parse_variant(store, institute_obj, case_obj, variant) for variant in
                        store.overlapping(variant_obj))

    # parse_gene function is not called for SVs, but a link to ensembl gene is required
    ensembl_link = ''
    for gene_obj in variant_obj['genes']:
        if gene_obj['common']:
            ensembl_id = gene_obj['common']['ensembl_id']
            build = int(gene_obj['common'].get('build','37'))
            gene_obj['ensembl_link'] = ensembl_link(ensembl_id, build=build)

    variant_obj['comments'] = store.events(institute_obj, case=case_obj,
                                           variant_id=variant_obj['variant_id'], comments=True)

    clinvar_submission = store.clinvars(variant_ids=[variant_id])
    if clinvar_submission:
        variant_obj['clinvar_submission_id'] = clinvar_submission[0]['clinvar_submission']

    return {
        'institute': institute_obj,
        'case': case_obj,
        'variant': variant_obj,
        'overlapping_snvs': overlapping_snvs,
        'manual_rank_options': MANUAL_RANK_OPTIONS,
        'dismiss_variant_options': DISMISS_VARIANT_OPTIONS
    }


def parse_variant(store, institute_obj, case_obj, variant_obj, update=False):
    """Parse information about variants."""
    has_changed = False
    compounds = variant_obj.get('compounds', [])
    if compounds:
        # Check if we need to add compound information
        # If it is the first time the case is viewed we fill in some compound information
        if 'not_loaded' not in compounds[0]:
            new_compounds = store.update_variant_compounds(variant_obj)
            variant_obj['compounds'] = new_compounds
            has_changed = True

        # sort compounds on combined rank score
        variant_obj['compounds'] = sorted(variant_obj['compounds'],
                                          key=lambda compound: -compound['combined_score'])

    genome_build = case_obj.get('genome_build','37')
    variant_genes = variant_obj.get('genes')
    if variant_genes is not None:
        for gene_obj in variant_genes:
            if not gene_obj['hgnc_id']:
                continue
            if gene_obj.get('hgnc_symbol') is None:
                hgnc_gene = store.hgnc_gene(gene_obj['hgnc_id'])
                if hgnc_gene:
                    has_changed = True
                    gene_obj['hgnc_symbol'] = hgnc_gene['hgnc_symbol']

    # We update the variant if some information was missing from loading
    if update and has_changed:
        variant_obj = store.update_variant(variant_obj)

    variant_obj['comments'] = store.events(institute_obj, case=case_obj,
                                           variant_id=variant_obj['variant_id'], comments=True)

    if variant_genes:
        variant_obj.update(get_predictions(variant_genes))
        if variant_obj.get('category') == 'cancer':
            variant_obj.update(get_variant_info(variant_genes))
    for compound_obj in compounds:
        compound_obj.update(get_predictions(compound_obj.get('genes', [])))

    if isinstance(variant_obj.get('acmg_classification'), int):
        acmg_code = ACMG_MAP[variant_obj['acmg_classification']]
        variant_obj['acmg_classification'] = ACMG_COMPLETE_MAP[acmg_code]

    # convert length for SV variants
    variant_length = variant_obj.get('length')
    variant_obj['length'] = {100000000000: 'inf', -1: 'n.d.'}.get(variant_length, variant_length)

    return variant_obj


def variant_export_lines(store, case_obj, variants_query):
    """Get variants info to be exported to file, one list (line) per variant.

        Args:
            store(scout.adapter.MongoAdapter)
            case_obj(scout.models.Case)
            variants_query: a list of variant objects, each one is a dictionary

        Returns:
            export_variants: a list of strings. Each string  of the list corresponding to the fields
                             of a variant to be exported to file, separated by comma
    """

    export_variants = []

    for variant in variants_query:
        variant_line = []
        position = variant['position']
        change = variant['reference']+'>'+variant['alternative']
        variant_line.append(variant['rank_score'])
        variant_line.append(variant['chromosome'])
        variant_line.append(position)
        variant_line.append(change)
        variant_line.append(str(position)+change)

        # gather gene info:
        gene_list = variant.get('genes') #this is a list of gene objects
        gene_ids = []
        gene_names = []
        hgvs_c = []

        # if variant is in genes
        if len(gene_list) > 0:
            for gene_obj in gene_list:
                hgnc_id = gene_obj['hgnc_id']
                gene_name = gene(store, hgnc_id)['symbol']

                gene_ids.append(hgnc_id)
                gene_names.append(gene_name)

                hgvs_nucleotide = '-'
                # gather HGVS info from gene transcripts
                transcripts_list = gene_obj.get('transcripts')
                for transcript_obj in transcripts_list:
                    if transcript_obj.get('is_canonical') and transcript_obj.get('is_canonical') is True:
                        hgvs_nucleotide = str(transcript_obj.get('coding_sequence_name'))
                hgvs_c.append(hgvs_nucleotide)

            variant_line.append(';'.join( str(x) for x in  gene_ids))
            variant_line.append(';'.join( str(x) for x in  gene_names))
            variant_line.append(';'.join( str(x) for x in  hgvs_c))
        else:
            while i < 4:
                variant_line.append('-') # instead of gene ids
                i = i+1

        variant_gts = variant['samples'] # list of coverage and gt calls for case samples
        for individual in case_obj['individuals']:
            for variant_gt in variant_gts:
                if individual['individual_id'] == variant_gt['sample_id']:
                    # gather coverage info
                    variant_line.append(variant_gt['allele_depths'][0]) # AD reference
                    variant_line.append(variant_gt['allele_depths'][1]) # AD alternate
                    # gather genotype quality info
                    variant_line.append(variant_gt['genotype_quality'])

        variant_line = [str(i) for i in variant_line]
        export_variants.append(",".join(variant_line))

    return export_variants


def variants_export_header(case_obj):
    """Returns a header for the CSV file with the filtered variants to be exported.

        Args:
            case_obj(scout.models.Case)

        Returns:
            header: includes the fields defined in scout.constants.variants_export EXPORT_HEADER
                    + AD_reference, AD_alternate, GT_quality for each sample analysed for a case
    """
    header = []
    header = header + EXPORT_HEADER
    # Add fields specific for case samples
    for individual in case_obj['individuals']:
        display_name = str(individual['display_name'])
        header.append('AD_reference_'+display_name) # Add AD reference field for a sample
        header.append('AD_alternate_'+display_name) # Add AD alternate field for a sample
        header.append('GT_quality_'+display_name) # Add Genotype quality field for a sample
    return header


def get_variant_info(genes):
    """Get variant information"""
    data = {'canonical_transcripts': []}
    for gene_obj in genes:
        if not gene_obj.get('canonical_transcripts'):
            tx = gene_obj['transcripts'][0]
            tx_id = tx['transcript_id']
            exon = tx.get('exon', '-')
            c_seq = tx.get('coding_sequence_name', '-')
        else:
            tx_id = gene_obj['canonical_transcripts']
            exon = gene_obj.get('exon', '-')
            c_seq = gene_obj.get('hgvs_identifier', '-')

        if len(c_seq) > 20:
            c_seq = c_seq[:20] + '...'

        if len(genes) == 1:
            value = ':'.join([tx_id,exon,c_seq])
        else:
            gene_id = gene_obj.get('hgnc_symbol') or str(gene_obj['hgnc_id'])
            value = ':'.join([gene_id, tx_id,exon,c_seq])
        data['canonical_transcripts'].append(value)

    return data


def get_predictions(genes):
    """Get sift predictions from genes."""
    data = {
        'sift_predictions': [],
        'polyphen_predictions': [],
        'region_annotations': [],
        'functional_annotations': [],
    }
    for gene_obj in genes:
        for pred_key in data:
            gene_key = pred_key[:-1]
            if len(genes) == 1:
                value = gene_obj.get(gene_key, '-')
            else:
                gene_id = gene_obj.get('hgnc_symbol') or str(gene_obj['hgnc_id'])
                value = ':'.join([gene_id, gene_obj.get(gene_key, '-')])
            data[pred_key].append(value)

    return data


def variant_case(store, case_obj, variant_obj):
    """Pre-process case for the variant view."""
    case_obj['bam_files'] = []
    case_obj['mt_bams'] = []
    case_obj['bai_files'] = []
    case_obj['mt_bais'] = []
    case_obj['sample_names'] = []
    for individual in case_obj['individuals']:
        bam_path = individual.get('bam_file')
        mt_bam = individual.get('mt_bam')
        case_obj['sample_names'].append(individual.get('display_name'))
        if bam_path and os.path.exists(bam_path):
            case_obj['bam_files'].append(individual['bam_file'])
            case_obj['bai_files'].append(find_bai_file(individual['bam_file']))
        if mt_bam and os.path.exists(mt_bam):
            case_obj['mt_bams'].append(individual['mt_bam'])
            case_obj['mt_bais'].append(find_bai_file(individual['mt_bam']))

        else:
            LOG.debug("%s: no bam file found", individual['individual_id'])

    try:
        genes = variant_obj.get('genes', [])
        if len(genes) == 1:
            hgnc_gene_obj = store.hgnc_gene(variant_obj['genes'][0]['hgnc_id'])
            if hgnc_gene_obj:
                vcf_path = store.get_region_vcf(case_obj, gene_obj=hgnc_gene_obj)
                case_obj['region_vcf_file'] = vcf_path
            else:
                case_obj['region_vcf_file'] = None
        elif len(genes) > 1:
            chrom = variant_obj['genes'][0]['common']['chromosome']
            start = min(gene['common']['start'] for gene in variant_obj['genes'])
            end = max(gene['common']['end'] for gene in variant_obj['genes'])
            vcf_path = store.get_region_vcf(case_obj, chrom=chrom, start=start, end=end)
            case_obj['region_vcf_file'] = vcf_path
    except (SyntaxError, Exception):
        LOG.warning("skip VCF region for alignment view")


def find_bai_file(bam_file):
    """Find out BAI file by extension given the BAM file."""
    bai_file = bam_file.replace('.bam', '.bai')
    if not os.path.exists(bai_file):
        # try the other convention
        bai_file = "{}.bai".format(bam_file)
    return bai_file


def variant(store, institute_obj, case_obj, variant_id=None):
    """Pre-process a single variant.

    Adds information from case and institute that is not present on the variant
    object

    Args:
        store(scout.adapter.MongoAdapter)
        institute_obj(scout.models.Institute)
        case_obj(scout.models.Case)
        variant_id(str)

    Returns:
        variant_info(dict): {
            'variant': <variant_obj>,
            'causatives': <list(other_causatives)>,
            'events': <list(events)>,
            'overlapping_svs': <list(overlapping svs)>,
            'manual_rank_options': MANUAL_RANK_OPTIONS,
            'dismiss_variant_options': DISMISS_VARIANT_OPTIONS,
            'ACMG_OPTIONS': ACMG_OPTIONS,
            'evaluations': <list(evaluations)>,
        }

    """
    default_panels = []
    # Add default panel information to variant
    for panel in case_obj['panels']:
        if not panel.get('is_default'):
            continue
        panel_obj = store.gene_panel(panel['panel_name'], panel.get('version'))
        if not panel:
            LOG.warning("Panel {0} version {1} could not be found".format(
                panel['panel_name'], panel.get('version')))
            continue
        default_panels.append(panel_obj)

    variant_obj = store.variant(variant_id, gene_panels=default_panels)
    genome_build = case_obj.get('genome_build', '37')

    if variant_obj is None:
        return None
    # Add information to case_obj
    variant_case(store, case_obj, variant_obj)
    events = list(store.events(institute_obj, case=case_obj, variant_id=variant_obj['variant_id']))
    for event in events:
        event['verb'] = VERBS_MAP[event['verb']]
    other_causatives = []
    for other_variant in store.other_causatives(case_obj, variant_obj):
        # This should work with old and new ids
        case_display_name = other_variant['case_id'].split('-', 1)[-1]
        other_variant['case_display_name'] = case_display_name
        other_causatives.append(other_variant)

    variant_obj = parse_variant(store, institute_obj, case_obj, variant_obj)
    variant_obj['end_position'] = end_position(variant_obj)
    variant_obj['frequency'] = frequency(variant_obj)
    variant_obj['clinsig_human'] = (clinsig_human(variant_obj) if variant_obj.get('clnsig')
                                    else None)
    variant_obj['thousandg_link'] = thousandg_link(variant_obj, genome_build)
    variant_obj['exac_link'] = exac_link(variant_obj)
    variant_obj['gnomad_link'] = gnomad_link(variant_obj)
    variant_obj['swegen_link'] = swegen_link(variant_obj)
    variant_obj['cosmic_link'] = cosmic_link(variant_obj)
    variant_obj['beacon_link'] = beacon_link(variant_obj, genome_build)
    variant_obj['ucsc_link'] = ucsc_link(variant_obj, genome_build)
    variant_obj['alamut_link'] = alamut_link(variant_obj)
    variant_obj['spidex_human'] = spidex_human(variant_obj)
    variant_obj['expected_inheritance'] = expected_inheritance(variant_obj)
    variant_obj['callers'] = callers(variant_obj, category='snv')

    for gene_obj in variant_obj.get('genes', []):
        parse_gene(gene_obj, genome_build)

    individuals = {individual['individual_id']: individual for individual in
                   case_obj['individuals']}
    for sample_obj in variant_obj['samples']:
        individual = individuals[sample_obj['sample_id']]
        sample_obj['is_affected'] = True if individual['phenotype'] == 2 else False

    gene_models = set()
    variant_obj['disease_associated_transcripts'] = []
    for gene_obj in variant_obj.get('genes', []):
        omim_models = set()
        for disease_term in gene_obj.get('disease_terms', []):
            omim_models.update(disease_term.get('inheritance', []))
        gene_obj['omim_inheritance'] = list(omim_models)
        for transcript_obj in gene_obj['transcripts']:
            if transcript_obj.get('is_disease_associated'):
                hgnc_symbol = (gene_obj['common']['hgnc_symbol'] if gene_obj['common'] else
                               gene_obj['hgnc_id'])
                refseq_id = transcript_obj['refseq_id']
                transcript_str = "{}:{}".format(hgnc_symbol, refseq_id)
                variant_obj['disease_associated_transcripts'].append(transcript_str)
        gene_models = gene_models | omim_models

    if variant_obj.get('genetic_models'):
        variant_models = set(model.split('_', 1)[0] for model in variant_obj['genetic_models'])
        variant_obj['is_matching_inheritance'] = variant_models & gene_models

    clinvar_submission = store.clinvars(variant_ids=[variant_obj['_id']])
    if clinvar_submission:
        variant_obj['clinvar_submission_id'] = clinvar_submission[0]['clinvar_submission']

    evaluations = []
    for evaluation_obj in store.get_evaluations(variant_obj):
        evaluation(store, evaluation_obj)
        evaluations.append(evaluation_obj)
    return {
        'variant': variant_obj,
        'causatives': other_causatives,
        'events': events,
        'overlapping_svs': (parse_variant(store, institute_obj, case_obj, variant_obj) for
                            variant_obj in store.overlapping(variant_obj)),
        'manual_rank_options': MANUAL_RANK_OPTIONS,
        'dismiss_variant_options': DISMISS_VARIANT_OPTIONS,
        'ACMG_OPTIONS': ACMG_OPTIONS,
        'evaluations': evaluations,
    }


def variants_filter_by_field(store, variants, field, case_obj, institute_obj):
    """Given a list of variant objects return only those that have a key specified
        by "field" and a value of this field not empty.

    Args:
        store(scout.adapter.MongoAdapter)
        variants(list(dict)): List of variant objects
        field(str): The key that indicates if variant is relevant
        case_obj(scout.models.Case)
        institute_obj(scout.models.Institute)

    Returns:
        filtered_variants(list): List of relevant variants
    """
    filtered_variants = []
    # Check if the variants have information if "field"
    for var in variants:
        if var.get(field):
            # Add more details to the variant
            if var['category'] == 'snv':
                var_object = variant(store, institute_obj, case_obj, var['_id'])
            else:
                var_object = sv_variant(store, institute_obj['_id'], case_obj['display_name'], var['_id'])

            filtered_variants.append(var_object['variant'])

    return filtered_variants


def observations(store, loqusdb, case_obj, variant_obj):
    """Query observations for a variant."""
    composite_id = ("{this[chromosome]}_{this[position]}_{this[reference]}_"
                    "{this[alternative]}".format(this=variant_obj))
    obs_data = loqusdb.get_variant({'_id': composite_id}) or {}
    obs_data['total'] = loqusdb.case_count()

    obs_data['cases'] = []
    institute_id = variant_obj['institute']
    for case_id in obs_data.get('families', []):
        if case_id != variant_obj['case_id'] and case_id.startswith(institute_id):
            other_variant = store.variant(variant_obj['variant_id'], case_id=case_id)
            other_case = store.case(case_id)
            obs_data['cases'].append(dict(case=other_case, variant=other_variant))

    return obs_data


def parse_gene(gene_obj, build=None):
    """Parse variant genes."""
    build = build or 37

    if gene_obj['common']:
        add_gene_links(gene_obj, build)

        refseq_transcripts = [transcript for transcript in gene_obj['transcripts'] if
                              transcript.get('refseq_id')]
        # select refseq transcripts as "primary" or use all Ensembl transcripts
        gene_obj['primary_transcripts'] = (refseq_transcripts if len(refseq_transcripts) > 0 else
                                           gene_obj['transcripts'])

    for tx_obj in gene_obj['transcripts']:
        parse_transcript(gene_obj, tx_obj, build)


def parse_transcript(gene_obj, tx_obj, build=None):
    """Parse variant gene transcript (VEP)."""
    build = build or 37
    add_tx_links(tx_obj, build)

    if tx_obj.get('refseq_id'):
        gene_name = (gene_obj['common']['hgnc_symbol'] if gene_obj['common'] else
                     gene_obj['hgnc_id'])
        tx_obj['change_str'] = transcript_str(tx_obj, gene_name)


def transcript_str(transcript_obj, gene_name=None):
    """Generate amino acid change as a string."""
    if transcript_obj.get('exon'):
        gene_part, part_count_raw = 'exon', transcript_obj['exon']
    elif transcript_obj.get('intron'):
        gene_part, part_count_raw = 'intron', transcript_obj['intron']
    else:
        # variant between genes
        gene_part, part_count_raw = 'intergenic', '0'

    part_count = part_count_raw.rpartition('/')[0]
    change_str = "{}:{}{}:{}:{}".format(
        transcript_obj.get('refseq_id', ''),
        gene_part,
        part_count,
        transcript_obj.get('coding_sequence_name', 'NA'),
        transcript_obj.get('protein_sequence_name', 'NA'),
    )
    if gene_name:
        change_str = "{}:".format(gene_name) + change_str
    return change_str


def end_position(variant_obj):
    """Calculate end position for a variant."""
    alt_bases = len(variant_obj['alternative'])
    num_bases = max(len(variant_obj['reference']), alt_bases)
    return variant_obj['position'] + (num_bases - 1)


def frequency(variant_obj):
    """Returns a judgement on the overall frequency of the variant.

    Combines multiple metrics into a single call.
    """
    most_common_frequency = max(variant_obj.get('thousand_genomes_frequency') or 0,
                                variant_obj.get('exac_frequency') or 0)
    if most_common_frequency > .05:
        return 'common'
    elif most_common_frequency > .01:
        return 'uncommon'
    else:
        return 'rare'


def clinsig_human(variant_obj):
    """Convert to human readable version of CLINSIG evaluation."""
    for clinsig_obj in variant_obj['clnsig']:
        # The clinsig objects allways have a accession
        if isinstance(clinsig_obj['accession'], int):
            # New version
            link = "https://www.ncbi.nlm.nih.gov/clinvar/variation/{}"
        else:
            # Old version
            link = "https://www.ncbi.nlm.nih.gov/clinvar/{}"

        human_str = 'not provided'
        if clinsig_obj.get('value'):
            try:
                # Old version
                int(clinsig_obj['value'])
                human_str = CLINSIG_MAP.get(clinsig_obj['value'], 'not provided')
            except ValueError:
                # New version
                human_str = clinsig_obj['value']

        clinsig_obj['human'] = human_str
        clinsig_obj['link'] = link.format(clinsig_obj['accession'])

        yield clinsig_obj


def thousandg_link(variant_obj, build=None):
    """Compose link to 1000G page for detailed information."""
    dbsnp_id = variant_obj.get('dbsnp_id')
    build = build or 37

    if not dbsnp_id:
        return None

    if build == 37:
        url_template = ("http://grch37.ensembl.org/Homo_sapiens/Variation/Explore"
                        "?v={};vdb=variation")
    else:
        url_template = ("http://www.ensembl.org/Homo_sapiens/Variation/Explore"
                        "?v={};vdb=variation")

    return url_template.format(dbsnp_id)


def exac_link(variant_obj):
    """Compose link to ExAC website for a variant position."""
    url_template = ("http://exac.broadinstitute.org/variant/"
                    "{this[chromosome]}-{this[position]}-{this[reference]}"
                    "-{this[alternative]}")
    return url_template.format(this=variant_obj)


def gnomad_link(variant_obj):
    """Compose link to gnomAD website."""
    url_template = ("http://gnomad.broadinstitute.org/variant/{this[chromosome]}-"
                    "{this[position]}-{this[reference]}-{this[alternative]}")
    return url_template.format(this=variant_obj)


def swegen_link(variant_obj):
    """Compose link to SweGen Variant Frequency Database."""
    url_template = ("https://swegen-exac.nbis.se/variant/{this[chromosome]}-"
                    "{this[position]}-{this[reference]}-{this[alternative]}")
    return url_template.format(this=variant_obj)

def cosmic_link(variant_obj):
    """Compose link to COSMIC Database.

    Args:
        variant_obj(scout.models.Variant)

    Returns:
        url_template(str): Link to COSMIIC database if cosmic id is present
    """

    cosmic_ids = variant_obj.get('cosmic_ids')

    if not cosmic_ids:
        return None
    else:
        cosmic_id = cosmic_ids[0]
        url_template = ("https://cancer.sanger.ac.uk/cosmic/mutation/overview?id={}")


    return url_template.format(cosmic_id)

def beacon_link(variant_obj, build=None):
    """Compose link to Beacon Network."""
    build = build or 37
    url_template = ("https://beacon-network.org/#/search?pos={this[position]}&"
                    "chrom={this[chromosome]}&allele={this[alternative]}&"
                    "ref={this[reference]}&rs=GRCh37")
    # beacon does not support build 38 at the moment
    # if build == '38':
    #     url_template = ("https://beacon-network.org/#/search?pos={this[position]}&"
    #                     "chrom={this[chromosome]}&allele={this[alternative]}&"
    #                     "ref={this[reference]}&rs=GRCh38")

    return url_template.format(this=variant_obj)


def ucsc_link(variant_obj, build=None):
    """Compose link to UCSC."""
    build = build or 37
    url_template = ("http://genome.ucsc.edu/cgi-bin/hgTracks?db=hg19&"
                        "position=chr{this[chromosome]}:{this[position]}"
                        "-{this[position]}&dgv=pack&knownGene=pack&omimGene=pack")
    if build == 38:
        url_template = ("http://genome.ucsc.edu/cgi-bin/hgTracks?db=hg20&"
                        "position=chr{this[chromosome]}:{this[position]}"
                        "-{this[position]}&dgv=pack&knownGene=pack&omimGene=pack")

    return url_template.format(this=variant_obj)


def alamut_link(variant_obj):
    url_template = ("http://localhost:10000/show?request={this[chromosome]}:"
                    "{this[position]}{this[reference]}>{this[alternative]}")
    return url_template.format(this=variant_obj)


def spidex_human(variant_obj):
    """Translate SPIDEX annotation to human readable string."""
    if variant_obj.get('spidex') is None:
        return 'not_reported'
    elif abs(variant_obj['spidex']) < SPIDEX_HUMAN['low']['pos'][1]:
        return 'low'
    elif abs(variant_obj['spidex']) < SPIDEX_HUMAN['medium']['pos'][1]:
        return 'medium'
    else:
        return 'high'


def expected_inheritance(variant_obj):
    """Gather information from common gene information."""
    manual_models = set()
    for gene in variant_obj.get('genes', []):
        manual_models.update(gene.get('manual_inheritance', []))
    return list(manual_models)


def callers(variant_obj, category='snv'):
    """Return info about callers."""
    calls = [(caller['name'], variant_obj.get(caller['id']))
             for caller in CALLERS[category] if variant_obj.get(caller['id'])]
    return calls


def sanger(store, mail, institute_obj, case_obj, user_obj, variant_obj, sender, url_builder =
url_for):
    """Send Sanger email."""
    variant_link = url_builder('variants.variant', institute_id=institute_obj['_id'],
                               case_name=case_obj['display_name'],
                               variant_id=variant_obj['_id'])
    if 'suspects' in case_obj and variant_obj['_id'] not in case_obj['suspects']:
        store.pin_variant(institute_obj, case_obj, user_obj, variant_link, variant_obj)

    recipients = institute_obj['sanger_recipients']
    if len(recipients) == 0:
        raise MissingSangerRecipientError()

    hgnc_symbol = ', '.join(variant_obj['hgnc_symbols'])
    gtcalls = ["<li>{}: {}</li>".format(sample_obj['display_name'],
                                        sample_obj['genotype_call'])
               for sample_obj in variant_obj['samples']]
    tx_changes = []
    for gene_obj in variant_obj.get('genes', []):
        for transcript_obj in gene_obj['transcripts']:
            parse_transcript(gene_obj, transcript_obj)
            if transcript_obj.get('change_str'):
                tx_changes.append("<li>{}</li>".format(transcript_obj['change_str']))

    html = """
      <ul">
        <li>
          <strong>Case {case_name}</strong>: <a href="{url}">{variant_id}</a>
        </li>
        <li><strong>HGNC symbols</strong>: {hgnc_symbol}</li>
        <li><strong>Gene panels</strong>: {panels}</li>
        <li><strong>GT call</strong></li>
        {gtcalls}
        <li><strong>Amino acid changes</strong></li>
        {tx_changes}
        <li><strong>Ordered by</strong>: {name}</li>
      </ul>
    """.format(case_name=case_obj['display_name'],
               url=variant_link,
               variant_id=variant_obj['display_name'],
               hgnc_symbol=hgnc_symbol,
               panels=', '.format(variant_obj['panels']),
               gtcalls=''.join(gtcalls),
               tx_changes=''.join(tx_changes),
               name=user_obj['name'].encode('utf-8'))

    kwargs = dict(subject="SCOUT: Sanger sequencing of {}".format(hgnc_symbol),
                  html=html, sender=sender, recipients=recipients,
                  # cc the sender of the email for confirmation
                  cc=[user_obj['email']])

    # compose and send the email message
    message = Message(**kwargs)
    mail.send(message)

    store.order_sanger(institute_obj, case_obj, user_obj, variant_link, variant_obj)


def cancel_sanger(store, mail, institute_obj, case_obj, user_obj, variant_obj, sender,
                  url_builder=url_for):
    """Send Sanger cancellation email."""
    variant_link = url_builder('variants.variant', institute_id=institute_obj['_id'],
                           case_name=case_obj['display_name'],
                           variant_id=variant_obj['_id'])
    # if 'suspects' in case_obj and variant_obj['_id'] not in case_obj['suspects']:
    #     store.pin_variant(institute_obj, case_obj, user_obj, variant_link, variant_obj)

    recipients = institute_obj['sanger_recipients']
    if len(recipients) == 0:
        raise MissingSangerRecipientError()

    hgnc_symbol = ', '.join(variant_obj['hgnc_symbols'])
    gtcalls = ["<li>{}: {}</li>".format(sample_obj['display_name'],
                                        sample_obj['genotype_call'])
               for sample_obj in variant_obj['samples']]
    tx_changes = []
    for gene_obj in variant_obj.get('genes', []):
        for transcript_obj in gene_obj['transcripts']:
            parse_transcript(gene_obj, transcript_obj)
            if transcript_obj.get('change_str'):
                tx_changes.append("<li>{}</li>".format(transcript_obj['change_str']))

    html = """
      <ul">
        <li>
          <strong>Case {case_name}</strong>: <a href="{url}">{variant_id}</a>
        </li>
        <li><strong>HGNC symbols</strong>: {hgnc_symbol}</li>
        <li><strong>Gene panels</strong>: {panels}</li>
        <li><strong>GT call</strong></li>
        {gtcalls}
        <li><strong>Amino acid changes</strong></li>
        {tx_changes}
        <li><strong>Order cancelled by</strong>: {name}</li>
      </ul>
    """.format(case_name=case_obj['display_name'],
               url=variant_link,
               variant_id=variant_obj['display_name'],
               hgnc_symbol=hgnc_symbol,
               panels=', '.format(variant_obj['panels']),
               gtcalls=''.join(gtcalls),
               tx_changes=''.join(tx_changes),
               name=user_obj['name'].encode('utf-8'))

    kwargs = dict(subject="SCOUT: Sanger sequencing of {} CANCELLED!".format(hgnc_symbol),
                  html=html, sender=sender, recipients=recipients,
                  # cc the sender of the email for confirmation
                  cc=[user_obj['email']])

    # compose and send the email message
    message = Message(**kwargs)
    mail.send(message)

    store.cancel_sanger(institute_obj, case_obj, user_obj, variant_link, variant_obj)


def cancer_variants(store, request_args, institute_id, case_name):
    """Fetch data related to cancer variants for a case."""
    institute_obj, case_obj = institute_and_case(store, institute_id, case_name)
    form = CancerFiltersForm(request_args)
    variants_query = store.variants(case_obj['_id'], category='cancer', query=form.data).limit(50)
    data = dict(
        institute=institute_obj,
        case=case_obj,
        variants=(parse_variant(store, institute_obj, case_obj, variant, update=True) for
                  variant in variants_query),
        form=form,
        variant_type=request_args.get('variant_type', 'clinical'),
    )
    return data

def clinvar_export(store, institute_id, case_name, variant_id):
    """Gather the required data for creating the clinvar submission form

        Args:
            store(scout.adapter.MongoAdapter)
            institute_id(str): Institute ID
            case_name(str): case ID
            variant_id(str): variant._id

        Returns:
            a dictionary with all the required data (case and variant level) to pre-fill in fields in the clinvar submission form

    """

    institute_obj, case_obj = institute_and_case(store, institute_id, case_name)
    pinned = [store.variant(variant_id) or variant_id for variant_id in
                  case_obj.get('suspects', [])]
    variant_obj = store.variant(variant_id)
    return dict(
        today = str(date.today()),
        institute=institute_obj,
        case=case_obj,
        variant=variant_obj,
        pinned_vars=pinned
    )

def get_clinvar_submission(store, institute_id, case_name, variant_id, submission_id):
    """Collects all variants from the clinvar submission collection with a specific submission_id

        Args:
            store(scout.adapter.MongoAdapter)
            institute_id(str): Institute ID
            case_name(str): case ID
            variant_id(str): variant._id
            submission_id(str): clinvar submission id, i.e. SUB76578

        Returns:
            A dictionary with all the data to display the clinvar_update.html template page
    """

    institute_obj, case_obj = institute_and_case(store, institute_id, case_name)
    pinned = [store.variant(variant_id) or variant_id for variant_id in
                  case_obj.get('suspects', [])]
    variant_obj = store.variant(variant_id)
    clinvar_submission_objs = store.clinvars(submission_id=submission_id)
    return dict(
        today = str(date.today()),
        institute=institute_obj,
        case=case_obj,
        variant=variant_obj,
        pinned_vars=pinned,
        clinvars = clinvar_submission_objs
    )


def variant_acmg(store, institute_id, case_name, variant_id):
    """Collect data relevant for rendering ACMG classification form."""
    institute_obj, case_obj = institute_and_case(store, institute_id, case_name)
    variant_obj = store.variant(variant_id)
    return dict(institute=institute_obj, case=case_obj, variant=variant_obj,
                CRITERIA=ACMG_CRITERIA, ACMG_OPTIONS=ACMG_OPTIONS)


def variant_acmg_post(store, institute_id, case_name, variant_id, user_email, criteria):
    """Calculate an ACMG classification based on a list of criteria."""
    institute_obj, case_obj = institute_and_case(store, institute_id, case_name)
    variant_obj = store.variant(variant_id)
    user_obj = store.user(user_email)
    variant_link = url_for('variants.variant', institute_id=institute_id,
                           case_name=case_name, variant_id=variant_id)
    classification = store.submit_evaluation(
        institute_obj=institute_obj,
        case_obj=case_obj,
        variant_obj=variant_obj,
        user_obj=user_obj,
        link=variant_link,
        criteria=criteria,
    )
    return classification


def evaluation(store, evaluation_obj):
    """Fetch and fill-in evaluation object."""
    evaluation_obj['institute'] = store.institute(evaluation_obj['institute_id'])
    evaluation_obj['case'] = store.case(evaluation_obj['case_id'])
    evaluation_obj['variant'] = store.variant(evaluation_obj['variant_specific'])
    evaluation_obj['criteria'] = {criterion['term']: criterion for criterion in
                                  evaluation_obj['criteria']}
    evaluation_obj['classification'] = ACMG_COMPLETE_MAP[evaluation_obj['classification']]
    return evaluation_obj


def upload_panel(store, institute_id, case_name, stream):
    """Parse out HGNC symbols from a stream."""
    institute_obj, case_obj = institute_and_case(store, institute_id, case_name)
    raw_symbols = [line.strip().split('\t')[0] for line in stream if
                   line and not line.startswith('#')]
    # check if supplied gene symbols exist
    hgnc_symbols = []
    for raw_symbol in raw_symbols:
        if store.hgnc_genes(raw_symbol).count() == 0:
            flash("HGNC symbol not found: {}".format(raw_symbol), 'warning')
        else:
            hgnc_symbols.append(raw_symbol)
    return hgnc_symbols
