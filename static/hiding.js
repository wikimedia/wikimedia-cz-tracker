{
	function processHiddencomment( el ) {
		const hiddencomment = el.querySelector( '.hiddencomment' ),
			unhide = el.querySelector( 'a.unhide' );

		hiddencomment.hidden = true;
		unhide.hidden = false;

		unhide.addEventListener( 'click', () => {
			hiddencomment.hidden = false;
			unhide.hidden = true;
		} );
	}

	document.addEventListener( 'DOMContentLoaded', () => {
		document.querySelectorAll( '.hide-switch' ).forEach( ( el ) => {
			processHiddencomment( el );
		} );
	} );
}
