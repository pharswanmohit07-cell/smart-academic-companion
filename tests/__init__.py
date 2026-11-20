"""Test package.

Importing this package pins the test environment and routes Supabase Auth to
the offline fake *before* any application module is imported.
"""

from tests.support import install_fake_auth, patch_auth_modules

install_fake_auth()
patch_auth_modules()
