from django.contrib.auth.forms import AdminPasswordChangeForm

from .services import set_user_password_and_revoke_tokens


class TokenRevokingAdminPasswordChangeForm(AdminPasswordChangeForm):
    """Apply admin password changes through the global revocation service."""

    def save(self, commit=True):
        if not commit:
            return super().save(commit=False)

        usable = self.cleaned_data.get('set_usable_password', True)
        raw_password = self.cleaned_data.get('password1') if usable else None
        return set_user_password_and_revoke_tokens(
            self.user,
            raw_password,
            usable=usable,
        )
