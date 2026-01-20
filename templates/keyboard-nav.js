// Keyboard navigation for browsing entries
(function() {
    const articles = document.querySelectorAll('article');
    const panel = document.getElementById('shortcuts-panel');
    const backdrop = document.getElementById('shortcuts-backdrop');
    let current = -1;

    function select(index) {
        if (articles[current]) articles[current].classList.remove('selected');
        current = Math.max(0, Math.min(index, articles.length - 1));
        articles[current].classList.add('selected');
        articles[current].scrollIntoView({ block: 'start', behavior: 'smooth' });
    }

    function toggleHelp() {
        panel.classList.toggle('hidden');
        backdrop.classList.toggle('hidden');
    }

    function closeHelp() {
        panel.classList.add('hidden');
        backdrop.classList.add('hidden');
    }

    backdrop.addEventListener('click', closeHelp);

    document.addEventListener('keydown', function(e) {
        // Ignore if typing in input/textarea
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

        if (e.key === 'j') {
            e.preventDefault();
            select(current + 1);
        }
        if (e.key === 'k') {
            e.preventDefault();
            select(current - 1);
        }
        if (e.key === '?') {
            e.preventDefault();
            toggleHelp();
        }
        if (e.key === 'Escape') {
            closeHelp();
        }
    });
})();
