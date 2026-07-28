from rest_framework import status
from rest_framework.response import Response
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


class QuantumTokenObtainPairSerializer(TokenObtainPairSerializer):

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        token["email"] = user.email
        token["username"] = user.username
        token["plan"] = user.plan
        token["verified"] = user.is_verified

        return token

    def validate(self, attrs):
        data = super().validate(attrs)

        data["success"] = True
        data["message"] = "Login Successful"

        data["user"] = {
            "id": str(self.user.id),
            "email": self.user.email,
            "username": self.user.username,
            "first_name": self.user.first_name,
            "last_name": self.user.last_name,
            "mobile": self.user.mobile,
            "plan": self.user.plan,
            "verified": self.user.is_verified,
            "avatar": (
                self.user.avatar.url
                if self.user.avatar
                else None
            ),
        }

        return data
