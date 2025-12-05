from django import forms
from .models import Job, Resume


class JobForm(forms.ModelForm):
    """Form for creating and editing job descriptions."""
    
    class Meta:
        model = Job
        fields = ['title', 'description', 'file', 'status', 'posted_date', 'closing_date']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500',
                'placeholder': 'e.g. Senior Python Developer'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500',
                'placeholder': 'Job requirements, responsibilities, qualifications...',
                'rows': 6
            }),
            'file': forms.FileInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500',
                'accept': '.pdf,.doc,.docx,.txt'
            }),
            'status': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500'
            }),
            'posted_date': forms.DateInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500',
                'type': 'date'
            }),
            'closing_date': forms.DateInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500',
                'type': 'date'
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


class ResumeForm(forms.ModelForm):
    """Form for creating and editing resumes."""
    
    class Meta:
        model = Resume
        fields = ['candidate_name', 'file', 'tier', 'recommendation', 
                  'experience_score', 'education_score', 'skills_score', 'final_score']
        widgets = {
            'candidate_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500',
                'placeholder': 'Enter candidate name'
            }),
            'file': forms.FileInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500',
                'accept': '.pdf,.doc,.docx'
            }),
            'tier': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500'
            }),
            'recommendation': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500'
            }),
            'experience_score': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500',
                'step': '0.01', 'min': '0', 'max': '100'
            }),
            'education_score': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500',
                'step': '0.01', 'min': '0', 'max': '100'
            }),
            'skills_score': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500',
                'step': '0.01', 'min': '0', 'max': '100'
            }),
            'final_score': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500',
                'step': '0.01', 'min': '0', 'max': '100'
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
