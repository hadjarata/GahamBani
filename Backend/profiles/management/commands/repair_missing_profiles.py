from django.core.management.base import BaseCommand

from accounts.models import User, UserRole
from profiles.services import repair_missing_patient_profile


class Command(BaseCommand):
    help = (
        'Crée les PatientProfile manquants sans données médicales fictives. '
        'Les médecins et administrateurs ne sont jamais modifiés.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Compte les profils manquants sans écrire en base.',
        )

    def handle(self, *args, **options):
        patient_ids = list(
            User.objects.filter(
                role=UserRole.PATIENT,
                patient_profile__isnull=True,
            ).values_list('pk', flat=True)
        )
        doctors_missing = User.objects.filter(
            role=UserRole.DOCTOR,
            doctor_profile__isnull=True,
        ).count()

        if options['dry_run']:
            self.stdout.write(
                'Simulation: '
                f'patients_sans_profil={len(patient_ids)} '
                f'medecins_sans_profil_ignores={doctors_missing} '
                'profils_crees=0'
            )
            return

        created = 0
        already_present = 0
        for user_id in patient_ids:
            _, was_created = repair_missing_patient_profile(user_id)
            if was_created:
                created += 1
            else:
                already_present += 1

        remaining = User.objects.filter(
            role=UserRole.PATIENT,
            patient_profile__isnull=True,
        ).count()
        self.stdout.write(self.style.SUCCESS(
            'Réparation terminée: '
            f'profils_crees={created} '
            f'deja_presents={already_present} '
            f'patients_sans_profil_restants={remaining} '
            f'medecins_sans_profil_ignores={doctors_missing}'
        ))
