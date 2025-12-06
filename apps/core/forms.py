from django import forms
from .models import Job, Resume


class JobForm(forms.ModelForm):
    """Form for creating and editing job descriptions."""
    
    class Meta:
        model = Job
        fields = ['title', 'description', 'status', 'posted_date', 'closing_date']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g. Senior Python Developer'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-input',
                'placeholder': 'Enter job requirements, responsibilities, and qualifications...',
                'rows': 8
            }),
            'status': forms.Select(attrs={
                'class': 'form-input'
            }),
            'posted_date': forms.DateInput(attrs={
                'class': 'form-input',
                'type': 'date'
            }),
            'closing_date': forms.DateInput(attrs={
                'class': 'form-input',
                'type': 'date'
            }),
        }
        labels = {
            'title': 'Job Title',
            'description': 'Job Description',
            'status': 'Status',
            'posted_date': 'Posted Date',
            'closing_date': 'Application Deadline',
        }


class ResumeForm(forms.ModelForm):
    """Form for creating and editing resumes - only name and file required, AI handles the rest."""
    
    class Meta:
        model = Resume
        fields = ['candidate_name', 'file']
        widgets = {
            'candidate_name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Enter candidate full name'
            }),
            'file': forms.FileInput(attrs={
                'class': 'form-input-file',
                'accept': '.pdf,.doc,.docx'
            }),
        }
        labels = {
            'candidate_name': 'Candidate Name',
            'file': 'Resume File',
        }
    
    def clean_file(self):
        """Validate file type, size, and content (magic byte check)."""
        file = self.cleaned_data.get('file')
        if file:
            # Check file size (max 5MB)
            max_size = 5 * 1024 * 1024  # 5MB
            if file.size > max_size:
                raise forms.ValidationError('File size must be under 5MB.')
            
            # Check file extension
            allowed_extensions = ['pdf', 'doc', 'docx']
            ext = file.name.split('.')[-1].lower()
            if ext not in allowed_extensions:
                raise forms.ValidationError(
                    f'Invalid file type. Allowed: {", ".join(allowed_extensions).upper()}'
                )
            
            # Magic byte validation - check file content matches extension
            file.seek(0)
            header = file.read(8)
            file.seek(0)  # Reset file pointer
            
            magic_bytes = {
                'pdf': b'%PDF',
                'docx': b'PK\x03\x04',  # ZIP format (DOCX is a ZIP)
                'doc': b'\xd0\xcf\x11\xe0',  # OLE compound document
            }
            
            expected_magic = magic_bytes.get(ext)
            if expected_magic and not header.startswith(expected_magic):
                raise forms.ValidationError(
                    f'File content does not match {ext.upper()} format. Please upload a valid file.'
                )
        return file
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.cleaned_data.get('file'):
            instance.file_name = self.cleaned_data['file'].name
            instance.file_type = self.cleaned_data['file'].name.split('.')[-1].lower()
        if commit:
            instance.save()
        return instance


class ResumeEditForm(forms.ModelForm):
    """Form for editing resumes - includes AI-generated fields that can be manually adjusted."""
    
    class Meta:
        model = Resume
        fields = ['candidate_name', 'file', 'tier', 'recommendation', 
                  'experience_score', 'education_score', 'skills_score', 'final_score']
        widgets = {
            'candidate_name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Enter candidate full name'
            }),
            'file': forms.FileInput(attrs={
                'class': 'form-input-file',
                'accept': '.pdf,.doc,.docx'
            }),
            'tier': forms.Select(attrs={
                'class': 'form-input'
            }),
            'recommendation': forms.Select(attrs={
                'class': 'form-input'
            }),
            'experience_score': forms.NumberInput(attrs={
                'class': 'form-input',
                'step': '0.1', 'min': '0', 'max': '100',
                'placeholder': '0-100'
            }),
            'education_score': forms.NumberInput(attrs={
                'class': 'form-input',
                'step': '0.1', 'min': '0', 'max': '100',
                'placeholder': '0-100'
            }),
            'skills_score': forms.NumberInput(attrs={
                'class': 'form-input',
                'step': '0.1', 'min': '0', 'max': '100',
                'placeholder': '0-100'
            }),
            'final_score': forms.NumberInput(attrs={
                'class': 'form-input',
                'step': '0.1', 'min': '0', 'max': '100',
                'placeholder': '0-100'
            }),
        }
        labels = {
            'candidate_name': 'Candidate Name',
            'file': 'Resume File',
            'tier': 'Tier',
            'recommendation': 'Decision',
            'experience_score': 'Experience Score',
            'education_score': 'Education Score',
            'skills_score': 'Skills Score',
            'final_score': 'Final Score',
        }
    
    def clean_file(self):
        """Validate file type, size, and content (magic byte check)."""
        file = self.cleaned_data.get('file')
        if file:
            max_size = 5 * 1024 * 1024
            if file.size > max_size:
                raise forms.ValidationError('File size must be under 5MB.')
            
            allowed_extensions = ['pdf', 'doc', 'docx']
            ext = file.name.split('.')[-1].lower()
            if ext not in allowed_extensions:
                raise forms.ValidationError(
                    f'Invalid file type. Allowed: {", ".join(allowed_extensions).upper()}'
                )
            
            # Magic byte validation
            file.seek(0)
            header = file.read(8)
            file.seek(0)
            
            magic_bytes = {
                'pdf': b'%PDF',
                'docx': b'PK\x03\x04',
                'doc': b'\xd0\xcf\x11\xe0',
            }
            
            expected_magic = magic_bytes.get(ext)
            if expected_magic and not header.startswith(expected_magic):
                raise forms.ValidationError(
                    f'File content does not match {ext.upper()} format.'
                )
        return file
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.cleaned_data.get('file'):
            instance.file_name = self.cleaned_data['file'].name
            instance.file_type = self.cleaned_data['file'].name.split('.')[-1].lower()
        if commit:
            instance.save()
        return instance
