from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('profiles', '0003_assignment_history_and_integrity'),
    ]

    operations = [
        migrations.AlterField(
            model_name='patientprofile',
            name='date_naissance',
            field=models.DateField(blank=True, null=True, verbose_name='date of birth'),
        ),
        migrations.AlterField(
            model_name='patientprofile',
            name='sexe',
            field=models.CharField(
                blank=True,
                choices=[
                    ('MALE', 'Male'),
                    ('FEMALE', 'Female'),
                    ('OTHER', 'Other'),
                ],
                max_length=10,
                null=True,
                verbose_name='sex',
            ),
        ),
        migrations.AlterField(
            model_name='patientprofile',
            name='poids',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=6,
                null=True,
                verbose_name='weight',
            ),
        ),
        migrations.AlterField(
            model_name='patientprofile',
            name='taille',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=5,
                null=True,
                verbose_name='height',
            ),
        ),
    ]
