"""Plain-language citizen timeline remarks per target state (EN / KN).
Kannada strings should be reviewed by a native speaker before the demo."""

SR_REMARKS: dict[str, tuple[str, str, str]] = {
    # to_state: (stage label, English remark, Kannada remark)
    "SUBMITTED": ("Grievance Registered", "Your grievance has been registered.", "ನಿಮ್ಮ ದೂರು ನೋಂದಾಯಿಸಲಾಗಿದೆ."),
    "ASSIGNED": ("Assigned to Officer", "Your grievance has been assigned to the ward officer.", "ನಿಮ್ಮ ದೂರನ್ನು ವಾರ್ಡ್ ಅಧಿಕಾರಿಗೆ ವಹಿಸಲಾಗಿದೆ."),
    "MERGED": ("Linked with Similar Report", "Your grievance was linked with an existing report of the same issue. You will keep receiving updates.", "ನಿಮ್ಮ ದೂರನ್ನು ಅದೇ ಸಮಸ್ಯೆಯ ಹಿಂದಿನ ದೂರಿನೊಂದಿಗೆ ಜೋಡಿಸಲಾಗಿದೆ. ನಿಮಗೆ ಮಾಹಿತಿ ಮುಂದುವರಿಯುತ್ತದೆ."),
    "REJECTED": ("Not Accepted", "Your grievance could not be accepted.", "ನಿಮ್ಮ ದೂರನ್ನು ಸ್ವೀಕರಿಸಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ."),
    "IN_PROGRESS": ("Work in Progress", "Work has started at the site.", "ಸ್ಥಳದಲ್ಲಿ ಕೆಲಸ ಪ್ರಾರಂಭವಾಗಿದೆ."),
    "ON_HOLD": ("On Hold", "Work is temporarily on hold.", "ಕೆಲಸವನ್ನು ತಾತ್ಕಾಲಿಕವಾಗಿ ತಡೆಹಿಡಿಯಲಾಗಿದೆ."),
    "WORK_COMPLETED": ("Work Completed", "The field team has reported the work as completed. It is being checked.", "ಕ್ಷೇತ್ರ ತಂಡವು ಕೆಲಸ ಮುಗಿದಿದೆ ಎಂದು ವರದಿ ಮಾಡಿದೆ. ಪರಿಶೀಲನೆ ನಡೆಯುತ್ತಿದೆ."),
    "VERIFIED": ("Work Verified", "The completed work has been verified by the Executive Engineer.", "ಪೂರ್ಣಗೊಂಡ ಕೆಲಸವನ್ನು ಕಾರ್ಯನಿರ್ವಾಹಕ ಎಂಜಿನಿಯರ್ ಪರಿಶೀಲಿಸಿದ್ದಾರೆ."),
    "RESOLVED": ("Resolved", "Your grievance has been resolved. Please confirm or reopen.", "ನಿಮ್ಮ ದೂರು ಪರಿಹರಿಸಲಾಗಿದೆ. ದಯವಿಟ್ಟು ದೃಢೀಕರಿಸಿ ಅಥವಾ ಮರುತೆರೆಯಿರಿ."),
    "CLOSED": ("Closed", "Your grievance is closed. Thank you.", "ನಿಮ್ಮ ದೂರು ಮುಕ್ತಾಯಗೊಂಡಿದೆ. ಧನ್ಯವಾದಗಳು."),
    "REOPENED": ("Reopened", "Your grievance has been reopened and will be investigated again.", "ನಿಮ್ಮ ದೂರನ್ನು ಮರುತೆರೆಯಲಾಗಿದೆ ಮತ್ತು ಮತ್ತೆ ಪರಿಶೀಲಿಸಲಾಗುವುದು."),
}

WO_REMARKS: dict[str, tuple[str, str, str]] = {
    "REWORK": ("Sent for Rework", "The completion photo did not pass checks; the work has been sent back to the crew.", "ಪೂರ್ಣಗೊಂಡ ಫೋಟೋ ಪರಿಶೀಲನೆಯಲ್ಲಿ ಉತ್ತೀರ್ಣವಾಗಲಿಲ್ಲ; ಕೆಲಸವನ್ನು ತಂಡಕ್ಕೆ ಹಿಂತಿರುಗಿಸಲಾಗಿದೆ."),
}
