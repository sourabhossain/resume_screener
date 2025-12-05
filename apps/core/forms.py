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
    """Form for creating and editing resumes."""
    
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
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.cleaned_data.get('file'):
            instance.file_name = self.cleaned_data['file'].name
            instance.file_type = self.cleaned_data['file'].name.split('.')[-1].lower()
        if commit:
            instance.save()
        return instance
