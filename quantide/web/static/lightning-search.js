(() => {
            if (window.__lightningAssetSearchBound) {
                return;
            }
            window.__lightningAssetSearchBound = true;

            function getInput() {
                return document.getElementById('lightning-asset-query');
            }

            function getDropdown() {
                return document.getElementById('lightning-asset-search-dropdown');
            }

            function hideDropdown() {
                const dropdown = getDropdown();
                if (!dropdown) {
                    return;
                }
                dropdown.innerHTML = '';
                dropdown.className = 'hidden';
            }

            document.body.addEventListener('click', function(evt) {
                const item = evt.target.closest('.lightning-asset-search-item');
                if (item) {
                    const input = getInput();
                    if (input) {
                        input.value = item.dataset.display || item.dataset.asset || '';
                    }
                    hideDropdown();
                    return;
                }

                if (!evt.target.closest('#lightning-asset-search-wrapper')) {
                    hideDropdown();
                }
            });

            document.body.addEventListener('keydown', function(evt) {
                const input = getInput();
                if (!input || evt.target !== input || evt.key !== 'Enter') {
                    return;
                }
                const firstItem = document.querySelector('.lightning-asset-search-item');
                if (!firstItem) {
                    return;
                }
                evt.preventDefault();
                input.value = firstItem.dataset.display || firstItem.dataset.asset || '';
                hideDropdown();
            });
        })();
