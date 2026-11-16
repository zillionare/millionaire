(function () {
            function setSidebarItemState(element, isActive) {
                if (!element) {
                    return;
                }
                element.classList.toggle('bg-[#fcfcfc]', isActive);
                element.classList.toggle('text-[#e41815]', isActive);
                element.classList.toggle('font-medium', isActive);
                element.classList.toggle('text-[#2c3030]', !isActive);
                element.classList.toggle('hover:bg-[#fcfcfc]', !isActive);
            }

            function normalizePath(path) {
                if (!path) {
                    return '/';
                }
                return path.length > 1 ? path.replace(/\/$/, '') : path;
            }

            function findSidebarLink(expectedPath, expectedHash, expectedLabel) {
                var links = document.querySelectorAll('aside a');
                for (var i = 0; i < links.length; i++) {
                    var link = links[i];
                    var href = link.getAttribute('href') || '';
                    var url = new URL(href, window.location.origin);
                    var label = (link.textContent || '').trim();
                    if (
                        normalizePath(url.pathname) === expectedPath
                        && url.hash === expectedHash
                    ) {
                        return link;
                    }
                    if (label === expectedLabel) {
                        return link;
                    }
                }
                return null;
            }

            function toggleStrategySections() {
                var strategySection = document.getElementById('strategy-list-section');
                var backtestSection = document.getElementById('backtest-list');
                if (!strategySection || !backtestSection) {
                    return;
                }
                var showBacktestOnly = window.location.hash === '#backtest-list';
                var strategyMenuLink = findSidebarLink('/strategy', '', '策略列表');
                var backtestMenuLink = findSidebarLink('/strategy', '#backtest-list', '回测报告');
                strategySection.classList.toggle('hidden', showBacktestOnly);
                backtestSection.classList.toggle('mt-0', showBacktestOnly);
                setSidebarItemState(strategyMenuLink, !showBacktestOnly);
                setSidebarItemState(backtestMenuLink, showBacktestOnly);
            }

            function handleSidebarToggleClick(event) {
                var link = event.target.closest('aside a');
                if (!link) {
                    return;
                }
                var url = new URL(link.href, window.location.origin);
                if (normalizePath(url.pathname) !== '/strategy') {
                    return;
                }
                var nextHash = url.hash || '';
                if (nextHash !== '' && nextHash !== '#backtest-list') {
                    return;
                }
                event.preventDefault();
                var nextUrl = url.pathname + url.search + nextHash;
                if (window.location.pathname + window.location.search + window.location.hash == nextUrl) {
                    toggleStrategySections();
                    return;
                }
                if (nextHash === window.location.hash) {
                    window.history.replaceState(null, '', nextUrl);
                } else {
                    window.history.pushState(null, '', nextUrl);
                }
                toggleStrategySections();
            }

            window.addEventListener('hashchange', toggleStrategySections);
            window.addEventListener('load', toggleStrategySections);
            window.addEventListener('pageshow', toggleStrategySections);
            document.addEventListener('click', handleSidebarToggleClick);
            toggleStrategySections();
        })();
