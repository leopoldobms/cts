from marshmallow import Schema, RAISE, fields


class AdditionalDataSchema(Schema):
    class Meta:
        unknown = RAISE

    deviceFingerprint = fields.Raw(allow_none=True)
