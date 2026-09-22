import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from argon2 import Type


path = Path(__file__).resolve().parents[1] / "deploy" / "migrate-user-profile.py"
spec = spec_from_file_location("migrate_user_profile", path)
module = module_from_spec(spec)
spec.loader.exec_module(module)


class UserProfileTests(unittest.TestCase):
    def test_password_uses_argon2id_and_can_be_verified(self):
        password = "example test password"
        encoded = module.PASSWORD_HASHER.hash(password)
        self.assertTrue(encoded.startswith("$argon2id$"))
        self.assertNotIn(password, encoded)
        self.assertTrue(module.PASSWORD_HASHER.verify(encoded, password))
        self.assertEqual(module.PASSWORD_HASHER.type, Type.ID)


if __name__ == "__main__":
    unittest.main()
