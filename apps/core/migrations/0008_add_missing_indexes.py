from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0007_add_organization_multi_tenant"),
    ]

    operations = [
        # Job: index on organization (most-queried filter)
        migrations.AddIndex(
            model_name="job",
            index=models.Index(fields=["organization"], name="job_org_idx"),
        ),
        migrations.AddIndex(
            model_name="job",
            index=models.Index(
                fields=["organization", "status"], name="job_org_status_idx"
            ),
        ),
        # Resume: index on organization + verification_status
        migrations.AddIndex(
            model_name="resume",
            index=models.Index(fields=["organization"], name="resume_org_idx"),
        ),
        migrations.AddIndex(
            model_name="resume",
            index=models.Index(
                fields=["verification_status"], name="resume_verification_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="resume",
            index=models.Index(
                fields=["organization", "screening_status"],
                name="resume_org_status_idx",
            ),
        ),
        # OrganizationMember: indexes on organization and user
        migrations.AddIndex(
            model_name="organizationmember",
            index=models.Index(fields=["organization"], name="orgmember_org_idx"),
        ),
        migrations.AddIndex(
            model_name="organizationmember",
            index=models.Index(fields=["user"], name="orgmember_user_idx"),
        ),
    ]
