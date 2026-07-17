from datetime import timedelta
from io import StringIO

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User, UserRole
from accounts.tokens import VersionedRefreshToken
from medical_audit.models import AuditAction, AuditDomain, MedicalAuditEvent

from .models import (
    AssignmentStatus,
    DoctorProfile,
    PatientDoctorAssignment,
    PatientProfile,
)
from .selectors import doctor_can_access_patient
from .services import (
    assign_doctor_to_patient,
    change_user_role,
    end_doctor_patient_assignment,
    get_profile_completion,
    repair_missing_patient_profile,
)


def authenticate(client, user):
    token = VersionedRefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.access_token}')


def create_patient_profile(user, **overrides):
    values = {
        'date_naissance': '1990-01-01',
        'sexe': 'FEMALE',
        'poids': '65.00',
        'taille': '168.00',
    }
    values.update(overrides)
    profile = PatientProfile(user=user, **values)
    profile.full_clean()
    profile.save()
    return profile


def create_doctor_profile(user, registration_number='MED-001', **overrides):
    values = {
        'specialite': 'Médecine interne',
        'numero_ordre': registration_number,
        'hopital': 'Hôpital central',
        'annees_experience': 8,
    }
    values.update(overrides)
    profile = DoctorProfile(user=user, **values)
    profile.full_clean()
    profile.save()
    return profile


class RepairMissingProfilesTests(TestCase):
    def setUp(self):
        self.patient = User.objects.create_user(
            email='repair-patient@example.com',
            password='SafePassword2026!',
            role=UserRole.PATIENT,
        )
        self.doctor = User.objects.create_user(
            email='repair-doctor@example.com',
            password='SafePassword2026!',
            role=UserRole.DOCTOR,
        )
        self.admin = User.objects.create_user(
            email='repair-admin@example.com',
            password='SafePassword2026!',
            role=UserRole.ADMIN,
        )

    def test_dry_run_reports_counts_without_writing_or_sensitive_values(self):
        stdout = StringIO()
        call_command('repair_missing_profiles', dry_run=True, stdout=stdout)

        output = stdout.getvalue()
        self.assertIn('patients_sans_profil=1', output)
        self.assertIn('medecins_sans_profil_ignores=1', output)
        self.assertIn('profils_crees=0', output)
        self.assertNotIn(self.patient.email, output)
        self.assertNotIn('SafePassword2026!', output)
        self.assertEqual(PatientProfile.objects.count(), 0)
        self.assertEqual(DoctorProfile.objects.count(), 0)

    def test_command_repairs_only_patients_and_is_idempotent(self):
        first_output = StringIO()
        call_command('repair_missing_profiles', stdout=first_output)

        profile = PatientProfile.objects.get(user=self.patient)
        self.assertIsNone(profile.date_naissance)
        self.assertIsNone(profile.sexe)
        self.assertIsNone(profile.poids)
        self.assertIsNone(profile.taille)
        self.assertFalse(DoctorProfile.objects.filter(user=self.doctor).exists())
        self.assertFalse(PatientProfile.objects.filter(user=self.admin).exists())
        self.assertIn('profils_crees=1', first_output.getvalue())

        second_output = StringIO()
        call_command('repair_missing_profiles', stdout=second_output)
        self.assertIn('profils_crees=0', second_output.getvalue())
        self.assertEqual(PatientProfile.objects.filter(user=self.patient).count(), 1)

    def test_service_is_idempotent_and_rejects_non_patient_roles(self):
        first, first_created = repair_missing_patient_profile(self.patient)
        second, second_created = repair_missing_patient_profile(self.patient.pk)

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first.pk, second.pk)
        with self.assertRaises(ValidationError):
            repair_missing_patient_profile(self.doctor)
        with self.assertRaises(ValidationError):
            repair_missing_patient_profile(self.admin)
        self.assertEqual(DoctorProfile.objects.count(), 0)


class ProfileIntegrityTests(TestCase):
    def setUp(self):
        self.patient_user = User.objects.create_user(
            email='patient@example.com',
            password='SafePassword2026!',
            role=UserRole.PATIENT,
        )
        self.doctor_user = User.objects.create_user(
            email='doctor@example.com',
            password='SafePassword2026!',
            role=UserRole.DOCTOR,
        )
        self.admin_user = User.objects.create_user(
            email='administrator@example.com',
            password='SafePassword2026!',
            role=UserRole.ADMIN,
        )

    def test_patient_profile_accepts_patient_and_is_unique_in_database(self):
        create_patient_profile(self.patient_user)

        with self.assertRaises(IntegrityError), transaction.atomic():
            PatientProfile.objects.create(
                user=self.patient_user,
                date_naissance='1991-01-01',
                sexe='OTHER',
                poids='70.00',
                taille='170.00',
            )

    def test_patient_profile_rejects_doctor_and_admin_roles(self):
        for user in (self.doctor_user, self.admin_user):
            profile = PatientProfile(
                user=user,
                date_naissance='1990-01-01',
                sexe='OTHER',
                poids='70.00',
                taille='170.00',
            )
            with self.subTest(role=user.role), self.assertRaises(ValidationError):
                profile.full_clean()

    def test_doctor_profile_accepts_doctor_and_is_unique_in_database(self):
        create_doctor_profile(self.doctor_user)

        with self.assertRaises(IntegrityError), transaction.atomic():
            DoctorProfile.objects.create(
                user=self.doctor_user,
                specialite='Cardiologie',
                numero_ordre='MED-002',
                hopital='Hôpital central',
                annees_experience=3,
            )

    def test_doctor_profile_rejects_patient_and_admin_roles(self):
        for index, user in enumerate((self.patient_user, self.admin_user), start=1):
            profile = DoctorProfile(
                user=user,
                specialite='Cardiologie',
                numero_ordre=f'MED-WRONG-{index}',
                hopital='Hôpital central',
                annees_experience=3,
            )
            with self.subTest(role=user.role), self.assertRaises(ValidationError):
                profile.full_clean()

    def test_same_user_cannot_have_compatible_patient_and_doctor_profiles(self):
        create_patient_profile(self.patient_user)
        doctor_profile = DoctorProfile(
            user=self.patient_user,
            specialite='Cardiologie',
            numero_ordre='MED-INCOMPATIBLE',
            hopital='Hôpital central',
            annees_experience=3,
        )

        with self.assertRaises(ValidationError):
            doctor_profile.full_clean()

    def test_registration_number_is_unique_in_database(self):
        create_doctor_profile(self.doctor_user, 'MED-UNIQUE')
        other_doctor = User.objects.create_user(
            email='other-doctor@example.com',
            password='SafePassword2026!',
            role=UserRole.DOCTOR,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            DoctorProfile.objects.create(
                user=other_doctor,
                specialite='Cardiologie',
                numero_ordre='MED-UNIQUE',
                hopital='Hôpital central',
                annees_experience=3,
            )


class AssignmentServiceTests(TestCase):
    def setUp(self):
        self.patient_user = User.objects.create_user(
            email='patient@example.com',
            password='SafePassword2026!',
            role=UserRole.PATIENT,
        )
        self.doctor_user = User.objects.create_user(
            email='doctor@example.com',
            password='SafePassword2026!',
            role=UserRole.DOCTOR,
        )
        self.patient = create_patient_profile(self.patient_user)
        self.doctor = create_doctor_profile(self.doctor_user)

    def assign(self):
        return assign_doctor_to_patient(
            doctor_user=self.doctor_user,
            patient_user=self.patient_user,
        )

    def test_valid_assignment_connects_doctor_and_patient(self):
        assignment = self.assign()

        self.assertEqual(assignment.status, AssignmentStatus.ACTIVE)
        self.assertIsNone(assignment.ended_at)
        self.assertIn(self.patient, self.doctor.patients.all())
        self.assertIn(self.doctor, self.patient.doctors.all())

    def test_wrong_roles_are_refused(self):
        User.objects.filter(pk=self.doctor_user.pk).update(role=UserRole.PATIENT)
        self.doctor_user.refresh_from_db()

        with self.assertRaises(ValidationError):
            self.assign()

        User.objects.filter(pk=self.doctor_user.pk).update(role=UserRole.DOCTOR)
        User.objects.filter(pk=self.patient_user.pk).update(role=UserRole.DOCTOR)
        self.doctor_user.refresh_from_db()
        self.patient_user.refresh_from_db()
        with self.assertRaises(ValidationError):
            self.assign()

    def test_missing_required_profile_is_refused(self):
        DoctorProfile.objects.filter(pk=self.doctor.pk).delete()

        with self.assertRaises(ValidationError):
            self.assign()

        self.doctor = create_doctor_profile(self.doctor_user, 'MED-RESTORED')
        PatientProfile.objects.filter(pk=self.patient.pk).delete()
        with self.assertRaises(ValidationError):
            self.assign()

    def test_second_active_assignment_is_refused_by_service(self):
        self.assign()

        with self.assertRaises(ValidationError):
            self.assign()

    def test_profile_and_assignment_history_are_protected_from_deletion(self):
        assignment = self.assign()

        with self.assertRaises(ProtectedError):
            self.doctor_user.delete()
        with self.assertRaises(ProtectedError):
            self.patient.delete()
        self.assertTrue(PatientDoctorAssignment.objects.filter(pk=assignment.pk).exists())

    def test_ending_then_reassigning_preserves_history(self):
        first = self.assign()
        ended = end_doctor_patient_assignment(first)
        second = self.assign()

        self.assertEqual(ended.status, AssignmentStatus.ENDED)
        self.assertIsNotNone(ended.ended_at)
        self.assertNotEqual(first.pk, second.pk)
        assignments = PatientDoctorAssignment.objects.filter(
            patient=self.patient,
            doctor=self.doctor,
        )
        self.assertEqual(assignments.count(), 2)
        self.assertEqual(assignments.filter(status=AssignmentStatus.ACTIVE).count(), 1)
        self.assertEqual(assignments.filter(status=AssignmentStatus.ENDED).count(), 1)

    def test_end_date_before_start_is_refused(self):
        assignment = self.assign()

        with self.assertRaises(ValidationError):
            end_doctor_patient_assignment(
                assignment,
                ended_at=assignment.assigned_at - timedelta(seconds=1),
            )

    def test_ended_assignment_cannot_be_reactivated(self):
        assignment = end_doctor_patient_assignment(self.assign())
        assignment.status = AssignmentStatus.ACTIVE
        assignment.ended_at = None

        with self.assertRaises(ValidationError):
            assignment.full_clean()

    def test_self_assignment_is_refused(self):
        with self.assertRaises(ValidationError):
            assign_doctor_to_patient(
                doctor_user=self.doctor_user,
                patient_user=self.doctor_user,
            )


class AssignmentDatabaseConstraintTests(TestCase):
    def setUp(self):
        patient_user = User.objects.create_user(
            email='sql-patient@example.com',
            password='SafePassword2026!',
            role=UserRole.PATIENT,
        )
        doctor_user = User.objects.create_user(
            email='sql-doctor@example.com',
            password='SafePassword2026!',
            role=UserRole.DOCTOR,
        )
        self.patient = create_patient_profile(patient_user)
        self.doctor = create_doctor_profile(doctor_user, 'MED-SQL')

    def test_database_rejects_duplicate_active_pair(self):
        PatientDoctorAssignment.objects.create(patient=self.patient, doctor=self.doctor)

        with self.assertRaises(IntegrityError), transaction.atomic():
            PatientDoctorAssignment.objects.create(patient=self.patient, doctor=self.doctor)

    def test_database_allows_multiple_ended_rows_for_pair(self):
        now = timezone.now()
        for offset in (2, 1):
            PatientDoctorAssignment.objects.create(
                patient=self.patient,
                doctor=self.doctor,
                status=AssignmentStatus.ENDED,
                assigned_at=now - timedelta(days=offset),
                ended_at=now - timedelta(days=offset, hours=-1),
            )

        self.assertEqual(PatientDoctorAssignment.objects.count(), 2)

    def test_database_rejects_end_date_before_start(self):
        now = timezone.now()
        with self.assertRaises(IntegrityError), transaction.atomic():
            PatientDoctorAssignment.objects.create(
                patient=self.patient,
                doctor=self.doctor,
                status=AssignmentStatus.ENDED,
                assigned_at=now,
                ended_at=now - timedelta(seconds=1),
            )

    def test_database_rejects_ended_status_without_end_date(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            PatientDoctorAssignment.objects.create(
                patient=self.patient,
                doctor=self.doctor,
                status=AssignmentStatus.ENDED,
            )


class DoctorPatientAccessTests(TestCase):
    def setUp(self):
        self.patient_user = User.objects.create_user(
            email='access-patient@example.com',
            password='SafePassword2026!',
            role=UserRole.PATIENT,
        )
        self.doctor_user = User.objects.create_user(
            email='access-doctor@example.com',
            password='SafePassword2026!',
            role=UserRole.DOCTOR,
        )
        create_patient_profile(self.patient_user)
        create_doctor_profile(self.doctor_user, 'MED-ACCESS')

    def test_active_assigned_doctor_has_access(self):
        assign_doctor_to_patient(
            doctor_user=self.doctor_user,
            patient_user=self.patient_user,
        )

        self.assertTrue(doctor_can_access_patient(self.doctor_user, self.patient_user))

    def test_unassigned_or_ended_assignment_does_not_grant_access(self):
        self.assertFalse(doctor_can_access_patient(self.doctor_user, self.patient_user))
        assignment = assign_doctor_to_patient(
            doctor_user=self.doctor_user,
            patient_user=self.patient_user,
        )
        end_doctor_patient_assignment(assignment)

        self.assertFalse(doctor_can_access_patient(self.doctor_user, self.patient_user))

    def test_inactive_doctor_or_patient_is_refused(self):
        assign_doctor_to_patient(
            doctor_user=self.doctor_user,
            patient_user=self.patient_user,
        )
        self.doctor_user.is_active = False
        self.assertFalse(doctor_can_access_patient(self.doctor_user, self.patient_user))
        self.doctor_user.is_active = True
        self.patient_user.is_active = False
        self.assertFalse(doctor_can_access_patient(self.doctor_user, self.patient_user))

    def test_wrong_roles_are_refused(self):
        assign_doctor_to_patient(
            doctor_user=self.doctor_user,
            patient_user=self.patient_user,
        )
        self.doctor_user.role = UserRole.PATIENT
        self.assertFalse(doctor_can_access_patient(self.doctor_user, self.patient_user))


class UserRoleTransitionTests(TestCase):
    def test_patient_with_profile_cannot_change_role(self):
        user = User.objects.create_user(
            email='role-patient@example.com',
            password='SafePassword2026!',
            role=UserRole.PATIENT,
        )
        create_patient_profile(user)
        user.role = UserRole.DOCTOR

        with self.assertRaises(ValidationError):
            user.save(update_fields=('role', 'updated_at'))
        user.refresh_from_db()
        self.assertEqual(user.role, UserRole.PATIENT)

    def test_doctor_with_profile_and_assignments_cannot_change_role(self):
        doctor_user = User.objects.create_user(
            email='role-doctor@example.com',
            password='SafePassword2026!',
            role=UserRole.DOCTOR,
        )
        patient_user = User.objects.create_user(
            email='role-doctor-patient@example.com',
            password='SafePassword2026!',
            role=UserRole.PATIENT,
        )
        create_doctor_profile(doctor_user, 'MED-ROLE')
        create_patient_profile(patient_user)
        assign_doctor_to_patient(doctor_user=doctor_user, patient_user=patient_user)

        with self.assertRaises(ValidationError):
            change_user_role(doctor_user, UserRole.PATIENT)

    def test_unchanged_role_is_allowed(self):
        user = User.objects.create_user(
            email='same-role@example.com',
            password='SafePassword2026!',
            role=UserRole.PATIENT,
        )
        create_patient_profile(user)

        result = change_user_role(user, UserRole.PATIENT)

        self.assertEqual(result.role, UserRole.PATIENT)

    def test_user_without_profile_can_change_role(self):
        user = User.objects.create_user(
            email='role-free@example.com',
            password='SafePassword2026!',
            role=UserRole.PATIENT,
        )

        change_user_role(user, UserRole.DOCTOR)

        user.refresh_from_db()
        self.assertEqual(user.role, UserRole.DOCTOR)

    def test_registered_admin_uses_model_validation_for_role_changes(self):
        user_admin = admin.site._registry[User]
        user = User.objects.create_user(
            email='admin-protected-patient@example.com',
            password='SafePassword2026!',
            role=UserRole.PATIENT,
        )
        create_patient_profile(user)
        request = RequestFactory().post('/')
        request.user = User(email='root@example.com', is_staff=True, is_superuser=True)
        form_class = user_admin.get_form(request, obj=user)
        form = form_class(
            instance=user,
            data={
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'phone': user.phone,
                'role': UserRole.ADMIN,
                'is_active': 'on',
                'is_verified': '',
                'is_staff': '',
                'is_superuser': '',
                'groups': [],
                'user_permissions': [],
            },
        )

        self.assertFalse(form.is_valid())
        self.assertIn('role', form.errors)


class ProfileAPITestMixin:
    def patient(self, email, **user_values):
        defaults = {
            'first_name': 'Awa', 'last_name': 'Traoré', 'phone': '+22370000000',
            'role': UserRole.PATIENT,
        }
        defaults.update(user_values)
        user = User.objects.create_user(email=email, password='SafePassword2026!', **defaults)
        return user, create_patient_profile(user)

    def doctor(self, email, registration, **user_values):
        defaults = {
            'first_name': 'Moussa', 'last_name': 'Diallo', 'phone': '+22371000000',
            'role': UserRole.DOCTOR,
        }
        defaults.update(user_values)
        user = User.objects.create_user(email=email, password='SafePassword2026!', **defaults)
        return user, create_doctor_profile(user, registration)


class CurrentProfileAPITests(ProfileAPITestMixin, APITestCase):
    def setUp(self):
        self.patient_user, self.patient_profile = self.patient('profile-patient@example.com')
        self.doctor_user, self.doctor_profile = self.doctor('profile-doctor@example.com', 'PROFILE-1')
        self.url = reverse('profiles:me')

    def test_patient_reads_only_safe_own_profile_and_complete_onboarding(self):
        authenticate(self.client, self.patient_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['profile_type'], UserRole.PATIENT)
        self.assertEqual(response.data['profile']['id'], str(self.patient_profile.pk))
        self.assertTrue(response.data['onboarding']['is_complete'])
        serialized = str(response.data).lower()
        for forbidden in ('antecedents', 'password', 'token_version', 'groups', 'permissions'):
            self.assertNotIn(forbidden, serialized)

    def test_patient_updates_whitelisted_fields_and_forbidden_fields_are_rejected(self):
        authenticate(self.client, self.patient_user)
        response = self.client.patch(self.url, {'poids': '70.50', 'sexe': 'MALE'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.patient_profile.refresh_from_db()
        self.assertEqual(str(self.patient_profile.poids), '70.50')
        for field, value in (
            ('role', UserRole.DOCTOR), ('user', str(self.doctor_user.pk)),
            ('id', str(self.doctor_profile.pk)), ('antecedents', 'secret'),
            ('created_at', timezone.now().isoformat()),
        ):
            with self.subTest(field=field):
                result = self.client.patch(self.url, {field: value}, format='json')
                self.assertEqual(result.status_code, 400)
        self.patient_user.refresh_from_db()
        self.assertEqual(self.patient_user.role, UserRole.PATIENT)

    def test_patient_validation_and_incomplete_onboarding(self):
        self.patient_user.first_name = ''
        self.patient_user.phone = ''
        self.patient_user.save(update_fields=('first_name', 'phone'))
        authenticate(self.client, self.patient_user)
        data = self.client.get(self.url).data
        self.assertFalse(data['onboarding']['is_complete'])
        self.assertEqual(data['onboarding']['completion_percentage'], 71)
        self.assertEqual(set(data['onboarding']['missing_fields']), {'first_name', 'phone'})
        self.assertEqual(self.client.patch(self.url, {'date_naissance': timezone.localdate().isoformat()}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(self.url, {'poids': '-1'}, format='json').status_code, 400)

    def test_doctor_reads_updates_public_professional_fields_but_not_registration(self):
        self.doctor_user.first_name = ''
        self.doctor_user.save(update_fields=('first_name',))
        authenticate(self.client, self.doctor_user)
        data = self.client.get(self.url).data
        self.assertEqual(data['profile_type'], UserRole.DOCTOR)
        self.assertEqual(data['profile']['numero_ordre'], 'PROFILE-1')
        self.assertFalse(data['onboarding']['is_complete'])
        self.assertIn('first_name', data['onboarding']['missing_fields'])
        response = self.client.patch(self.url, {'specialite': ' Cardiologie ', 'hopital': 'Hôpital B'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.doctor_profile.refresh_from_db()
        self.assertEqual(self.doctor_profile.specialite, 'Cardiologie')
        for field in ('numero_ordre', 'role', 'user', 'updated_at'):
            self.assertEqual(self.client.patch(self.url, {field: 'forbidden'}, format='json').status_code, 400)

    def test_missing_profile_inactive_account_and_admin_are_refused(self):
        missing = User.objects.create_user(email='missing-profile@example.com', password='x', role=UserRole.PATIENT)
        authenticate(self.client, missing)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        inactive, _ = self.patient('profile-inactive@example.com', is_active=False)
        authenticate(self.client, inactive)
        self.assertEqual(self.client.get(self.url).status_code, 401)
        admin_user = User.objects.create_user(email='profile-admin@example.com', password='x', role=UserRole.ADMIN)
        authenticate(self.client, admin_user)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_me_has_constant_query_count_and_is_audited(self):
        authenticate(self.client, self.patient_user)
        with self.assertNumQueries(5):
            self.client.get(self.url)
        event = MedicalAuditEvent.objects.get(domain=AuditDomain.PROFILES)
        self.assertEqual(event.action, AuditAction.VIEW)
        self.assertEqual(event.patient_id, self.patient_profile.pk)
        self.assertNotIn('profile', str(event.metadata).lower().replace('own_profile', ''))

    def test_patch_audit_only_contains_changed_field_names(self):
        authenticate(self.client, self.doctor_user)
        self.client.patch(self.url, {'hopital': 'Nouvel établissement'}, format='json')
        event = MedicalAuditEvent.objects.get(domain=AuditDomain.PROFILES)
        self.assertEqual(event.metadata['changed_fields'], ['hopital'])
        self.assertNotIn('Nouvel établissement', str(event.metadata))


class AssignmentProfileAPITests(ProfileAPITestMixin, APITestCase):
    def setUp(self):
        self.patient_user, self.patient_profile = self.patient('assign-patient@example.com')
        self.other_patient_user, self.other_patient = self.patient('assign-other-patient@example.com')
        self.doctor_user, self.doctor_profile = self.doctor('assign-doctor@example.com', 'ASSIGN-1')
        self.other_doctor_user, self.other_doctor = self.doctor('assign-other-doctor@example.com', 'ASSIGN-2')
        self.active = assign_doctor_to_patient(doctor_user=self.doctor_user, patient_user=self.patient_user)
        self.other_pair = assign_doctor_to_patient(doctor_user=self.other_doctor_user, patient_user=self.other_patient_user)

    def test_doctor_sees_only_active_current_patients_without_medical_data(self):
        second_active_user, second_active = self.patient('assign-second-active@example.com')
        assign_doctor_to_patient(doctor_user=self.doctor_user, patient_user=second_active_user)
        ended_user, ended_profile = self.patient('assign-ended@example.com')
        ended = assign_doctor_to_patient(doctor_user=self.doctor_user, patient_user=ended_user)
        end_doctor_patient_assignment(ended)
        inactive_user, inactive_profile = self.patient('assign-inactive-patient@example.com')
        assign_doctor_to_patient(doctor_user=self.doctor_user, patient_user=inactive_user)
        inactive_user.is_active = False
        inactive_user.save(update_fields=('is_active',))
        authenticate(self.client, self.doctor_user)
        response = self.client.get(reverse('profiles:my-patients'))
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(
            {row['patient_profile_id'] for row in response.data['results']},
            {str(self.patient_profile.pk), str(second_active.pk)},
        )
        row = response.data['results'][0]
        for forbidden in ('email', 'antecedents', 'treatment', 'measure', 'document', 'poids'):
            self.assertNotIn(forbidden, str(row).lower())

    def test_patient_sees_only_active_doctors_and_public_fields(self):
        second_user, second_profile = self.doctor('assign-second-doctor@example.com', 'ASSIGN-3')
        assign_doctor_to_patient(doctor_user=second_user, patient_user=self.patient_user)
        ended_user, _ = self.doctor('assign-ended-doctor@example.com', 'ASSIGN-4')
        ended = assign_doctor_to_patient(doctor_user=ended_user, patient_user=self.patient_user)
        end_doctor_patient_assignment(ended)
        inactive_user, _ = self.doctor('assign-inactive-doctor@example.com', 'ASSIGN-5')
        assign_doctor_to_patient(doctor_user=inactive_user, patient_user=self.patient_user)
        inactive_user.is_active = False
        inactive_user.save(update_fields=('is_active',))
        authenticate(self.client, self.patient_user)
        response = self.client.get(reverse('profiles:my-doctors'))
        self.assertEqual(response.data['count'], 2)
        self.assertEqual({row['doctor_profile_id'] for row in response.data['results']}, {str(self.doctor_profile.pk), str(second_profile.pk)})
        serialized = str(response.data).lower()
        self.assertNotIn('numero_ordre', serialized)
        self.assertNotIn('email', serialized)

    def test_role_specific_lists_and_no_uuid_detail_endpoint(self):
        authenticate(self.client, self.patient_user)
        self.assertEqual(self.client.get(reverse('profiles:my-patients')).status_code, 403)
        authenticate(self.client, self.doctor_user)
        self.assertEqual(self.client.get(reverse('profiles:my-doctors')).status_code, 403)
        self.assertEqual(self.client.get(f'/api/profiles/{self.patient_profile.pk}/').status_code, 404)

    def test_history_contains_only_own_active_and_ended_rows_with_filters_pagination(self):
        ended_doctor_user, _ = self.doctor('history-ended@example.com', 'HISTORY-1')
        ended = assign_doctor_to_patient(doctor_user=ended_doctor_user, patient_user=self.patient_user)
        end_doctor_patient_assignment(ended)
        authenticate(self.client, self.patient_user)
        url = reverse('profiles:assignments')
        all_rows = self.client.get(url, {'page_size': 1})
        self.assertEqual(all_rows.data['count'], 2)
        self.assertEqual(len(all_rows.data['results']), 1)
        ordered = self.client.get(url, {'ordering': 'assigned_at'}).data['results']
        self.assertLessEqual(ordered[0]['assigned_at'], ordered[1]['assigned_at'])
        ended_rows = self.client.get(url, {'status': AssignmentStatus.ENDED})
        self.assertEqual(ended_rows.data['count'], 1)
        self.assertEqual(ended_rows.data['results'][0]['status'], AssignmentStatus.ENDED)
        self.assertNotIn(str(self.other_pair.pk), str(all_rows.data))
        self.assertFalse(doctor_can_access_patient(ended_doctor_user, self.patient_user))

    def test_invalid_filters_and_pagination_bound(self):
        authenticate(self.client, self.patient_user)
        url = reverse('profiles:assignments')
        self.assertEqual(self.client.get(url, {'status': 'UNKNOWN'}).status_code, 400)
        self.assertEqual(self.client.get(url, {'date_from': timezone.now().isoformat(), 'date_to': (timezone.now() - timedelta(days=1)).isoformat()}).status_code, 400)
        self.assertEqual(self.client.get(url, {'page_size': 101}).status_code, 400)

    def test_assignment_routes_are_read_only_and_me_allows_patch_only(self):
        authenticate(self.client, self.doctor_user)
        for route in ('my-patients', 'assignments'):
            url = reverse(f'profiles:{route}')
            for method in ('post', 'put', 'patch', 'delete'):
                self.assertEqual(getattr(self.client, method)(url, {}, format='json').status_code, 405)
        authenticate(self.client, self.patient_user)
        for route in ('my-doctors', 'assignments'):
            url = reverse(f'profiles:{route}')
            for method in ('post', 'put', 'patch', 'delete'):
                self.assertEqual(getattr(self.client, method)(url, {}, format='json').status_code, 405)
        me = reverse('profiles:me')
        self.assertEqual(self.client.post(me, {}, format='json').status_code, 405)
        self.assertEqual(self.client.put(me, {}, format='json').status_code, 405)
        self.assertEqual(self.client.delete(me).status_code, 405)

    def test_list_query_counts_are_constant_and_audited(self):
        authenticate(self.client, self.doctor_user)
        with self.assertNumQueries(7):
            self.client.get(reverse('profiles:my-patients'))
        authenticate(self.client, self.patient_user)
        with self.assertNumQueries(7):
            self.client.get(reverse('profiles:my-doctors'))
        with self.assertNumQueries(7):
            self.client.get(reverse('profiles:assignments'))
        self.assertEqual(MedicalAuditEvent.objects.filter(domain=AuditDomain.PROFILES, action=AuditAction.LIST).count(), 3)

    def test_openapi_contains_routes_onboarding_and_polymorphic_profiles(self):
        authenticate(self.client, self.patient_user)
        response = self.client.get(reverse('schema'))
        content = response.content.decode()
        for route in ('me', 'my-patients', 'my-doctors', 'assignments'):
            self.assertIn(f'/api/profiles/{route}/', content)
        self.assertIn('CurrentProfileResponse', content)
        self.assertIn('completion_percentage', content)
