from django.db import migrations, models

FONTE_2022 = ('IBGE Censo 2022 (renda/urbanização/alfabetização/faixa etária/PIB); '
              'Portal da Transparência (Bolsa Família); Gov.br (MEI)')


def backfill_fonte(apps, schema_editor):
    """§5.4: registra a proveniência dos indicadores já existentes (ano 2022)."""
    Ind = apps.get_model('mapa', 'IndicadorMunicipal')
    Ind.objects.filter(ano_referencia=2022, fonte='').update(fonte=FONTE_2022)


def limpar_fonte(apps, schema_editor):
    Ind = apps.get_model('mapa', 'IndicadorMunicipal')
    Ind.objects.filter(fonte=FONTE_2022).update(fonte='')


class Migration(migrations.Migration):
    """§5.3: campo 'anos_estudo_medio' guardava a TAXA DE ALFABETIZAÇÃO (%) —
    renomeado para 'taxa_alfabetizacao' (rótulo = conteúdo). §5.4: adiciona 'fonte'
    para proveniência do indicador. RenameField preserva os dados."""

    dependencies = [
        ('mapa', '0007_remove_resultadocandidato_mapa_result_is_sorg_d56bb5_idx_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='indicadormunicipal',
            old_name='anos_estudo_medio',
            new_name='taxa_alfabetizacao',
        ),
        migrations.AlterField(
            model_name='indicadormunicipal',
            name='taxa_alfabetizacao',
            field=models.DecimalField(decimal_places=1, default=0, max_digits=4, verbose_name='Taxa de alfabetização (%)'),
        ),
        migrations.AddField(
            model_name='indicadormunicipal',
            name='fonte',
            field=models.CharField(blank=True, max_length=200, verbose_name='Fonte'),
        ),
        migrations.RunPython(backfill_fonte, limpar_fonte),
    ]
