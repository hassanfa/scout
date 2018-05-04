import logging

from pprint import pprint as pp

from click import progressbar

from scout.utils.requests import fetch_ensembl_transcripts
from scout.parse.ensembl import parse_transcripts
from scout.build.genes.transcript import build_transcript

LOG = logging.getLogger(__name__)

TRANSCRIPT_CATEGORIES = ['mrna', 'nc_rna', 'mrna_predicted']

def load_transcripts(adapter, transcripts_lines=None, build='37', ensembl_genes=None):
    """Load all the transcripts

    Transcript information is from ensembl.

    Args:
        adapter(MongoAdapter)
        transcripts_lines(iterable): iterable with ensembl transcript lines
        build(str)
        ensembl_genes(dict): Map from ensembl_id -> HgncGene

    Returns:
        transcript_objs(list): A list with all transcript objects
    """
    # Fetch all genes with ensemblid as keys
    ensembl_genes = ensembl_genes or adapter.ensembl_genes(build)
    LOG.info("Number of genes: {0}".format(len(ensembl_genes)))

    if not transcripts_lines:
        transcripts_lines = fetch_ensembl_transcripts(build=build)

    transcripts_dict = parse_transcripts(transcripts_lines)
    
    for ens_gene_id in transcripts_dict:
        parsed_tx = transcripts_dict[ens_gene_id]
        # Fetch the internal gene object to find out the correct hgnc id
        gene_obj = ensembl_genes.get(ens_gene_id)
        # If the gene is non existing in scout we skip the transcript
        if not gene_obj:
            transcripts_dict.pop(ens_gene_id)
            LOG.debug("Gene %s does not exist in build %s", ens_gene_id, build)
            continue
        
        # Add the correct hgnc id
        parsed_tx['hgnc_id'] = gene_obj['hgnc_id']
        # Primary transcript information is collected from HGNC
        parsed_tx['primary_transcripts'] = set(gene_obj.get('primary_transcripts', []))

    ref_seq_transcripts = 0
    nr_primary_transcripts = 0
    nr_transcripts = len(transcripts_dict)

    transcript_objs = []

    with progressbar(transcripts_dict.values(), label="Building transcripts", length=nr_transcripts) as bar:
        for tx_data in bar:

            #################### Get the correct refseq identifier ####################
            # We need to decide one refseq identifier for each transcript, if there are any to choose 
            # from. The algorithm is as follows:
            # If these is ONE mrna this is choosen
            # If there are several mrna the one that is in 'primary_transcripts' is choosen
            # Else one is choosen at random
            # The same follows for the other categories where nc_rna has precedense over mrna_predicted
            tx_data['is_primary'] = False
            primary_transcripts = tx_data['primary_transcripts']
            refseq_identifier = None
            for category in TRANSCRIPT_CATEGORIES:
                identifiers = tx_data[category]
                if not identifiers:
                    continue

                intersection = identifiers.intersection(primary_transcripts)
                ref_seq_transcripts += 1
                if intersection:
                    refseq_identifier = intersection.pop()
                    tx_data['is_primary'] = True
                    nr_primary_transcripts += 1
                else:
                    refseq_identifier = identifiers.pop()
                # If there was refseq identifiers we break the loop
                break

            if refseq_identifier:
                tx_data['refseq_id'] = refseq_identifier
            ####################  ####################  ####################

            # Build the transcript object
            tx_obj = build_transcript(tx_data, build)
            transcript_objs.append(tx_obj)

    # Load all transcripts
    LOG.info("Loading transcripts...")
    if len(transcript_objs) > 0:
        adapter.load_transcript_bulk(transcript_objs)

    LOG.info('Number of transcripts in build %s: %s', build, nr_transcripts)
    LOG.info('Number of transcripts with refseq identifier: %s', ref_seq_transcripts)
    LOG.info('Number of primary transcripts: %s', nr_primary_transcripts)

    return transcript_objs
    