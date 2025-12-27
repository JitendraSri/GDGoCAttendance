const socket = io({ transports: ['websocket'] });

// Initial Stats Load
fetch('/api/stats')
    .then(response => response.json())
    .then(updateStats)
    .catch(err => console.error(err));

// Socket IO Listeners
socket.on('update_counts', (data) => {
    updateStats(data);
});

function updateStats(data) {
    if (!data) return;
    document.getElementById('totalCount').innerText = data.total;
    if (data.total_students !== undefined) {
        document.getElementById('totalStudents').innerText = data.total_students;
    }

    const grid = document.getElementById('branchGrid');
    grid.innerHTML = '';

    for (const [branch, count] of Object.entries(data.branch_counts)) {
        const item = document.createElement('div');
        item.className = 'branch-item';
        item.innerHTML = `
            <span class="branch-name">${branch}</span>
            <span class="branch-count">${count}</span>
        `;
        grid.appendChild(item);
    }
}

// QR Code Scanner Logic
let html5QrcodeScanner;

function onScanSuccess(decodedText, decodedResult) {
    // Prevent multiple rapid scans? Maybe throttle.
    // Ideally pause scanner or just process.
    console.log(`Scan result: ${decodedText}`);
    markAttendance(decodedText);
}

function onScanFailure(error) {
    // handle scan failure, usually better to ignore and keep scanning.
    // console.warn(`Code scan error = ${error}`);
}

// Initialize Scanner on Load
document.addEventListener("DOMContentLoaded", () => {
    html5QrcodeScanner = new Html5QrcodeScanner(
        "reader",
        { fps: 10, qrbox: { width: 250, height: 250 } },
        /* verbose= */ false);
    html5QrcodeScanner.render(onScanSuccess, onScanFailure);
});

// Manual Entry
function handleManualEntry() {
    const input = document.getElementById('manualRollInput');
    const roll = input.value;
    if (roll) {
        markAttendance(roll);
        input.value = '';
    }
}

// Mark Attendance Function
function markAttendance(rollNumber) {
    const resultDiv = document.getElementById('scanResult');
    resultDiv.innerHTML = 'Processing...';
    resultDiv.className = 'scan-result';

    fetch('/api/mark_attendance', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ roll_number: rollNumber })
    })
        .then(response => response.json().then(data => ({ status: response.status, body: data })))
        .then(({ status, body }) => {
            if (status === 200) {
                resultDiv.innerText = `Success: ${body.name} (${body.branch})`;
                resultDiv.className = 'scan-result success';
                // Play success sound?
            } else if (status === 409) {
                resultDiv.innerText = `Duplicate: Already marked today.`;
                resultDiv.className = 'scan-result warning';
            } else if (status === 404) {
                resultDiv.innerText = `Student not found.`;
                resultDiv.className = 'scan-result error';
                openAddStudentModal(body.roll_number);
            } else {
                resultDiv.innerText = `Error: ${body.error || 'Unknown error'}`;
                resultDiv.className = 'scan-result error';
            }
        })
        .catch(err => {
            resultDiv.innerText = `Network Error`;
            resultDiv.className = 'scan-result error';
            console.error(err);
        });
}

// Add Student Modal Logic
const modal = document.getElementById("addStudentModal");
const span = document.getElementsByClassName("close-modal")[0];
let pendingRollNumber = null;

function openAddStudentModal(rollNumber) {
    pendingRollNumber = rollNumber;
    document.getElementById('modalRollNumber').innerText = rollNumber;
    document.getElementById('newStudentName').value = '';
    modal.style.display = "block";
    // Pause scanner
    if (html5QrcodeScanner) {
        html5QrcodeScanner.pause();
    }
}

span.onclick = function () {
    closeModal();
}

// Close modal when clicking outside
window.onclick = function (event) {
    if (event.target == modal) {
        closeModal();
    }
}

// View List Logic
let currentBranchFilter = 'ALL';

function openViewListModal() {
    document.getElementById('viewListModal').style.display = 'block';
    filterList('ALL');
}

function closeModal(modalId) {
    if (modalId) {
        document.getElementById(modalId).style.display = 'none';
        if (modalId === 'addStudentModal') pendingRollNumber = null;
    } else {
        // Fallback or generic close
        document.querySelectorAll('.modal').forEach(m => m.style.display = 'none');
        pendingRollNumber = null;
    }

    // Resume scanner if it was paused
    if (html5QrcodeScanner) {
        try {
            html5QrcodeScanner.resume();
        } catch (e) {
            // ignore
        }
    }
}

function filterList(branch) {
    currentBranchFilter = branch;

    // Update Active Tab
    document.querySelectorAll('.tab-btn').forEach(btn => {
        if (btn.innerText === branch) btn.classList.add('active');
        else btn.classList.remove('active');
    });

    // Update Download Link
    const downloadBtn = document.getElementById('downloadCurrentPdf');
    if (branch === 'ALL') {
        downloadBtn.style.display = 'none'; // Or allow downloading comprehensive?
        // User requested branch wise download. Let's hide for ALL to stay safe or make it inactive.
        downloadBtn.href = '#';
        downloadBtn.innerText = 'Select Branch to Download';
    } else {
        downloadBtn.style.display = 'inline-block';
        downloadBtn.href = `/download_pdf/${branch}`;
        downloadBtn.innerText = `Download ${branch} PDF`;
    }

    // Fetch Data
    fetch(`/api/attendees?branch=${branch}`)
        .then(res => res.json())
        .then(data => {
            renderTable(data);
        })
        .catch(err => console.error(err));
}

function renderTable(data) {
    const tbody = document.getElementById('attendeesTableBody');
    tbody.innerHTML = '';

    if (data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; padding: 1rem;">No attendees found.</td></tr>';
        return;
    }

    data.forEach(row => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td style="padding: 0.5rem; border-bottom: 1px solid #dadce0;">${row.s_no}</td>
            <td style="padding: 0.5rem; border-bottom: 1px solid #dadce0;">${row.rollResult}</td>
            <td style="padding: 0.5rem; border-bottom: 1px solid #dadce0;">${row.name}</td>
            <td style="padding: 0.5rem; border-bottom: 1px solid #dadce0;">${row.branch}</td>
            <td style="padding: 0.5rem; border-bottom: 1px solid #dadce0;">
                <button onclick="deleteFromList('${row.rollResult}')" style="background-color: #d93025; color: white; border: none; padding: 4px 8px; border-radius: 4px; cursor: pointer; font-size: 0.8rem;">Delete</button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function deleteFromList(rollNumber) {
    if (!confirm(`Are you sure you want to PERMANENTLY DELETE ${rollNumber}?`)) {
        return;
    }

    fetch('/api/delete_student', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ roll_number: rollNumber })
    })
        .then(async response => {
            const text = await response.text();
            try {
                const data = JSON.parse(text);
                if (!response.ok) throw new Error(data.message || `Error ${response.status}`);
                return data;
            } catch (e) {
                throw new Error(`Server returned non-JSON: ${response.status} ${text.substring(0, 50)}...`);
            }
        })
        .then(data => {
            alert(data.message);
            // Refresh the list
            filterList(currentBranchFilter);
        })
        .catch(err => {
            alert("Action Failed: " + err.message);
            console.error("Delete Error:", err);
        });
}


function submitNewStudent() {
    const name = document.getElementById('newStudentName').value;
    if (!name) {
        alert("Please enter a name.");
        return;
    }

    if (!pendingRollNumber) return;

    fetch('/api/add_student', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ roll_number: pendingRollNumber, name: name })
    })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'SUCCESS') {
                const resultDiv = document.getElementById('scanResult');
                resultDiv.innerText = `Added & Marked: ${name}`;
                resultDiv.className = 'scan-result success';
                closeModal();
            } else {
                alert("Error adding student: " + (data.error || 'Unknown'));
            }
        })
        .catch(err => {
            alert("Network Error");
            console.error(err);
        });
}

// Delete Student Logic
function handleDeleteStudent() {
    const rollInput = document.getElementById('deleteRollInput');
    const rollNumber = rollInput.value;

    if (!rollNumber) {
        alert("Enter roll number to delete");
        return;
    }

    if (!confirm(`Are you sure you want to PERMANENTLY DELETE ${rollNumber}?`)) {
        return;
    }

    const resultDiv = document.getElementById('deleteResult');
    resultDiv.innerText = 'Deleting...';
    resultDiv.className = 'scan-result';

    fetch('/api/delete_student', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ roll_number: rollNumber })
    })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'SUCCESS') {
                resultDiv.innerText = data.message;
                resultDiv.className = 'scan-result success';
                rollInput.value = '';
            } else {
                resultDiv.innerText = data.message;
                resultDiv.className = 'scan-result error';
            }
        })
        .catch(err => {
            resultDiv.innerText = 'Network Error';
            resultDiv.className = 'scan-result error';
            console.error(err);
        });
}
