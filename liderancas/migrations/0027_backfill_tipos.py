from django.db import migrations

def preencher(apps, schema_editor):
    Lideranca = apps.get_model('liderancas', 'Lideranca')
    # backfill via all_objects não existe no historical model; usa o manager base
    for o in Lideranca.objects.filter(tipo__gt='').exclude(tipo=''):
        if not o.tipos:
            o.tipos = [o.tipo]
            o.save(update_fields=['tipos'])

def reverter(apps, schema_editor):
    pass

class Migration(migrations.Migration):
    dependencies = [('liderancas', '0026_lideranca_tipos')]
    operations = [migrations.RunPython(preencher, reverter)]
