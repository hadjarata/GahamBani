import uuid
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import User, UserRole
from alerts.services import evaluate_measurement_for_alerts
from medical_records.models import (
    Allergy, BloodGroupChoices, ChronicDisease, Consultation, MedicalRecord,
    SeverityChoices, StatusChoices, Treatment, TreatmentStatus,
)
from monitoring.models import BloodGlucose, BloodPressure, GlucoseUnit, MealContext
from profiles.models import DoctorProfile, PatientDoctorAssignment, PatientProfile
from profiles.services import assign_doctor_to_patient, end_doctor_patient_assignment


DEMO_NAMESPACE = uuid.UUID('f414f0f7-5ee4-4b5c-a7d3-6112d5081d5d')
PATIENT_EMAIL = 'demo.gahambani+patient@example.invalid'
DOCTOR_EMAIL = 'demo.gahambani+doctor@example.invalid'
FORMER_DOCTOR_EMAIL = 'demo.gahambani+former-doctor@example.invalid'
LOCAL_DEFAULT_PASSWORD = 'Demo-Local-Only-Change-Me-2026!'


def demo_id(label):
    return uuid.uuid5(DEMO_NAMESPACE, label)


class Command(BaseCommand):
    help = 'Crée des données entièrement fictives et idempotentes pour l’intégration mobile locale.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--password', default=LOCAL_DEFAULT_PASSWORD,
            help='Mot de passe local des comptes fictifs. Ne jamais réutiliser en staging/production.',
        )

    def _user(self, email, role, first_name, last_name, phone, password):
        user, _ = User.objects.update_or_create(
            email=email,
            defaults={
                'role': role, 'first_name': first_name, 'last_name': last_name,
                'phone': phone, 'is_active': True, 'is_verified': True,
            },
        )
        user.set_password(password)
        user.save(update_fields=('password', 'updated_at'))
        return user

    def handle(self, *args, **options):
        if not getattr(settings, 'ALLOW_DEMO_DATA', False):
            raise CommandError('seed_demo_data est interdit hors environnement de développement autorisé.')
        password = options['password']
        if len(password) < 12:
            raise CommandError('Le mot de passe de démonstration doit contenir au moins 12 caractères.')
        return self._seed(password)

    @transaction.atomic
    def _seed(self, password):
        now = timezone.now().replace(microsecond=0)
        today = timezone.localdate()
        patient_user = self._user(
            PATIENT_EMAIL, UserRole.PATIENT, 'DEMO-PATIENT-001', 'FICTIF',
            '+223000000001', password,
        )
        doctor_user = self._user(
            DOCTOR_EMAIL, UserRole.DOCTOR, 'DEMO-MEDECIN-001', 'FICTIF',
            '+223000000002', password,
        )
        former_doctor_user = self._user(
            FORMER_DOCTOR_EMAIL, UserRole.DOCTOR, 'DEMO-ANCIEN-MEDECIN', 'FICTIF',
            '+223000000003', password,
        )
        patient, _ = PatientProfile.objects.update_or_create(
            user=patient_user,
            defaults={
                'date_naissance': '1990-01-01', 'sexe': 'OTHER',
                'poids': Decimal('70.00'), 'taille': Decimal('170.00'),
                'antecedents': 'DEMO — données entièrement fictives.',
            },
        )
        doctor, _ = DoctorProfile.objects.update_or_create(
            user=doctor_user,
            defaults={
                'specialite': 'DEMO — spécialité fictive',
                'numero_ordre': 'DEMO-ORDRE-0001', 'hopital': 'DEMO — établissement fictif',
                'annees_experience': 8,
            },
        )
        former_doctor, _ = DoctorProfile.objects.update_or_create(
            user=former_doctor_user,
            defaults={
                'specialite': 'DEMO — ancienne spécialité fictive',
                'numero_ordre': 'DEMO-ORDRE-0002', 'hopital': 'DEMO — ancien établissement fictif',
                'annees_experience': 5,
            },
        )

        if not PatientDoctorAssignment.objects.filter(
            patient=patient, doctor=doctor, status='ACTIVE', ended_at__isnull=True,
        ).exists():
            assign_doctor_to_patient(doctor_user=doctor_user, patient_user=patient_user, assigned_at=now - timedelta(days=120))
        if not PatientDoctorAssignment.objects.filter(patient=patient, doctor=former_doctor).exists():
            old = assign_doctor_to_patient(
                doctor_user=former_doctor_user, patient_user=patient_user,
                assigned_at=now - timedelta(days=300),
            )
            end_doctor_patient_assignment(old, ended_at=now - timedelta(days=200))

        record, _ = MedicalRecord.objects.update_or_create(
            patient=patient,
            defaults={'groupe_sanguin': BloodGroupChoices.UNKNOWN, 'antecedents_familiaux': 'DEMO — historique familial fictif.'},
        )
        ChronicDisease.objects.update_or_create(
            id=demo_id('chronic-disease'),
            defaults={
                'medical_record': record, 'nom_maladie': 'DEMO — condition chronique fictive',
                'date_diagnostic': today - timedelta(days=500), 'gravite': SeverityChoices.LOW,
                'statut': StatusChoices.ACTIVE, 'notes': 'DEMO uniquement.',
            },
        )
        Allergy.objects.update_or_create(
            id=demo_id('allergy'),
            defaults={
                'medical_record': record, 'nom': 'DEMO — allergène fictif',
                'gravite': SeverityChoices.LOW, 'reaction': 'DEMO — réaction fictive',
                'is_active': True, 'notes': 'DEMO uniquement.',
            },
        )
        Treatment.objects.update_or_create(
            id=demo_id('treatment'),
            defaults={
                'medical_record': record, 'nom_medicament': 'DEMO-MEDICAMENT-FICTIF',
                'description': 'Produit fictif sans usage réel.', 'dosage': 'DEMO-DOSE',
                'frequence': 'DEMO-FREQUENCE', 'voie_administration': 'DEMO',
                'date_debut': today - timedelta(days=60), 'date_fin': None,
                'prescrit_par': doctor_user, 'statut': TreatmentStatus.ACTIVE,
                'notes': 'Ne constitue pas une prescription réelle.',
            },
        )
        Consultation.objects.update_or_create(
            id=demo_id('consultation'),
            defaults={
                'patient': patient, 'medecin': doctor,
                'date_consultation': now - timedelta(days=30),
                'motif': 'DEMO — consultation fictive d’intégration.',
                'diagnostic': 'DEMO — aucun diagnostic réel.',
                'symptomes': 'DEMO', 'observations': 'DEMO', 'notes': 'DEMO uniquement.',
            },
        )

        pressure_values = [(28, 122, 78, 70), (14, 128, 82, 74), (2, 190, 125, 135)]
        for index, (days, systolic, diastolic, heart_rate) in enumerate(pressure_values):
            measurement, _ = BloodPressure.objects.update_or_create(
                id=demo_id(f'pressure-{index}'),
                defaults={
                    'patient': patient, 'systolique': systolic, 'diastolique': diastolic,
                    'frequence_cardiaque': heart_rate, 'date_mesure': now - timedelta(days=days),
                    'notes': 'DEMO — mesure fictive.',
                },
            )
            measurement.full_clean()
            evaluate_measurement_for_alerts(measurement, actor=patient_user)

        glucose_values = [(25, '1.05', GlucoseUnit.G_PER_L), (12, '115', GlucoseUnit.MG_PER_DL), (1, '2.60', GlucoseUnit.G_PER_L)]
        for index, (days, value, unit) in enumerate(glucose_values):
            measurement, _ = BloodGlucose.objects.update_or_create(
                id=demo_id(f'glucose-{index}'),
                defaults={
                    'patient': patient, 'valeur': Decimal(value), 'unite': unit,
                    'hba1c': Decimal('8.20') if index == 2 else None,
                    'contexte_repas': MealContext.BEFORE_MEAL,
                    'date_mesure': now - timedelta(days=days), 'notes': 'DEMO — mesure fictive.',
                },
            )
            measurement.full_clean()
            evaluate_measurement_for_alerts(measurement, actor=patient_user)

        self.stdout.write(self.style.SUCCESS('Données DEMO créées ou mises à jour sans doublons.'))
        self.stdout.write(f'Patient: {PATIENT_EMAIL}')
        self.stdout.write(f'Médecin: {DOCTOR_EMAIL}')
        if password == LOCAL_DEFAULT_PASSWORD:
            self.stdout.write(self.style.WARNING('Mot de passe local par défaut utilisé; remplacez-le avec --password.'))
