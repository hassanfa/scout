import logging

import click

log = logging.getLogger(__name__)

@click.command('case', short_help='Update a case')
@click.argument('case_id', required=False)
@click.option('--case-name', '-n',
                help="A display name of case",
)
@click.option('--institute', '-i',
                help="Specify the institutes of the case",
)
@click.option('--add-collaborator', '-c',
                help="Add a collaborator to the case",
)
@click.option('--vcf', type=click.Path(exists=True),
              help='path to clinical VCF file to be added')
@click.option('--vcf-sv', type=click.Path(exists=True),
              help='path to clinical SV VCF file to be added')
@click.option('--vcf-cancer', type=click.Path(exists=True),
              help='path to clinical cancer VCF file to be added')
@click.option('--vcf-research', type=click.Path(exists=True),
              help='path to research VCF file to be added')
@click.option('--vcf-sv-research', type=click.Path(exists=True),
              help='path to research VCF with sv variants to be added')
@click.option('--vcf-cancer-research', type=click.Path(exists=True),
              help='path to research VCF with cancer variants to be added')
@click.option('--peddy-ped', type=click.Path(exists=True),
              help='path to outfile .peddy.ped from peddy')
@click.pass_context
def case(context, case_id, case_name, institute, add_collaborator, vcf, vcf_sv,
         vcf_cancer, vcf_research, vcf_sv_research, vcf_cancer_research, peddy_ped):
    """
    Update a case in the database
    """
    adapter = context.obj['adapter']
    if not case_id:
        if not (case_name and institute):
            log.info("Please specify which case to update.")
            context.abort
        case_id = "{0}-{1}".format(institute, case_name)
    # Chock if the case exists
    case_obj = adapter.case(case_id)
    
    if not case_obj:
        log.warning("Case %s could not be found", case_id)
        context.abort()
    
    if add_collaborator:
        if not adapter.institute(add_collaborator):
            log.warning("Institute %s could not be found", add_collaborator)
            context.abort()
        if not add_collaborator in case_obj['collaborators']:
            case_obj['collaborators'].append(add_collaborator)
            log.info("Adding collaborator %s", add_collaborator)
    
    if vcf:
        log.info("Updating 'vcf_snv' to %s", vcf)
        case_obj['vcf_files']['vcf_snv'] = vcf
    if vcf_sv:
        log.info("Updating 'vcf_sv' to %s", vcf_sv)
        case_obj['vcf_files']['vcf_sv'] = vcf_sv
    if vcf_cancer:
        log.info("Updating 'vcf_cancer' to %s", vcf_cancer)
        case_obj['vcf_files']['vcf_cancer'] = vcf_cancer
    if vcf_research:
        log.info("Updating 'vcf_research' to %s", vcf_research)
        case_obj['vcf_files']['vcf_research'] = vcf_research
    if vcf_sv_research:
        log.info("Updating 'vcf_sv_research' to %s", vcf_sv_research)
        case_obj['vcf_files']['vcf_sv_research'] = vcf_sv_research
    if vcf_cancer_research:
        log.info("Updating 'vcf_cancer_research' to %s", vcf_cancer_research)
        case_obj['vcf_files']['vcf_cancer_research'] = vcf_cancer_research

    adapter.update_case(case_obj)
