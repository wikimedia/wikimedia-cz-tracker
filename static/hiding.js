{
	function processHiddencomment( el ) {
		const hiddencomment = el.querySelector( 'div.hiddencomment' ),
			unhide = el.querySelector( 'button.unhide' );

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
